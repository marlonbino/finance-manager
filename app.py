from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from io import BytesIO
import os
import re
from sqlalchemy import func, inspect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'data', 'finance.db'))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH.replace(os.sep, '/')}"
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    phone = db.Column(db.String(30), unique=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    onboarding_done = db.Column(db.Boolean, default=False)

class IncomeSource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, default=0)
    date_received = db.Column(db.DateTime, default=datetime.now)
    notes = db.Column(db.String(200))

class Kitty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    percentage = db.Column(db.Float, nullable=False)
    current_balance = db.Column(db.Float, default=0)
    monthly_cap = db.Column(db.Float, nullable=True)
    color = db.Column(db.String(7), default='#6366f1')
    transactions = db.relationship('Transaction', foreign_keys='Transaction.kitty_id', backref='kitty', cascade='all, delete-orphan')

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    kitty_id = db.Column(db.Integer, db.ForeignKey('kitty.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.now)
    type = db.Column(db.String(20), default='spending')  # spending, transfer_out, transfer_in
    related_kitty_id = db.Column(db.Integer, db.ForeignKey('kitty.id'), nullable=True)
    
def normalize_phone(phone):
    digits = re.sub(r'\D+', '', phone or '')
    if digits.startswith('0') and len(digits) == 10:
        digits = '254' + digits[1:]
    elif len(digits) == 9:
        digits = '254' + digits
    return digits

def month_bounds(year, month):
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end

def previous_month_bounds(reference=None):
    reference = reference or datetime.now()
    current_start = datetime(reference.year, reference.month, 1)
    previous_end = current_start
    previous_start = datetime(previous_end.year - 1, 12, 1) if previous_end.month == 1 else datetime(previous_end.year, previous_end.month - 1, 1)
    return previous_start, previous_end

def money(value):
    return f"KES {float(value or 0):,.0f}"

def fmt_period_date(iso_date):
    try:
        return datetime.strptime(iso_date, '%Y-%m-%d').strftime('%d %b %Y')
    except (TypeError, ValueError):
        return str(iso_date or '')

def short_label(value, limit=18):
    value = str(value or '')
    return value if len(value) <= limit else value[:limit - 1] + '.'

def status_color(status):
    return {
        'healthy': colors.HexColor('#0f766e'),
        'low': colors.HexColor('#f59e0b'),
        'depleted': colors.HexColor('#dc2626'),
        'fast': colors.HexColor('#2563eb'),
    }.get(status, colors.HexColor('#64727f'))

def status_label(status):
    return {
        'healthy': 'On track',
        'low': 'Running low',
        'depleted': 'Empty',
        'fast': 'Spending faster',
    }.get(status, str(status).title())

def coverage_bar_color(pct):
    if pct >= 100:
        return colors.HexColor('#0f766e')
    if pct >= 50:
        return colors.HexColor('#2563eb')
    if pct > 0:
        return colors.HexColor('#d97706')
    return colors.HexColor('#dc2626')

def pdf_header_table_style(bg='#0f766e'):
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(bg)),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#d6ddd9')),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('PADDING', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])

def pdf_label_value_table_style():
    return TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f3f1')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#cbd5d1')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('PADDING', (0, 0), (-1, -1), 7),
    ])

def summary_cards(summary):
    net = float(summary.get('net_flow', 0))
    net_text = ('+' if net >= 0 else '−') + money(abs(net))
    net_color = colors.HexColor('#0f766e') if net >= 0 else colors.HexColor('#dc2626')
    coverage = summary.get('overall_coverage_pct', 0)
    need = float(summary.get('projected_next_month_need', 0))
    coverage_text = f"{coverage:.0f}%" if need > 0 else '—'
    cards = [
        ['Total available', money(summary['total_balance']), colors.HexColor('#0f766e')],
        ['Period net', net_text, net_color],
        ['Next month ready', coverage_text, colors.HexColor('#6d28d9')],
    ]
    row = []
    for label, value, color in cards:
        row.append(Table(
            [[label], [value]],
            colWidths=[155],
            style=TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), color),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, 1), 14),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ])
        ))
    return Table([row], colWidths=[165] * len(row))

def wallet_fill_color(hex_color, default='#0f766e'):
    raw = str(hex_color or default).lstrip('#')
    if len(raw) == 6:
        return colors.HexColor(f'#{raw}')
    return colors.HexColor(default)

def _empty_chart_drawing(title, message, height=200):
    drawing = Drawing(480, height)
    drawing.add(String(0, height - 18, title, fontName='Helvetica-Bold', fontSize=11, fillColor=colors.HexColor('#172026')))
    drawing.add(String(0, height - 50, message, fontSize=9, fillColor=colors.HexColor('#64727f')))
    return drawing

def wallet_pie_chart(kitties, value_key, title, empty_message='No data to chart.'):
    rows = [k for k in kitties if float(k.get(value_key, 0)) > 0]
    if not rows:
        return _empty_chart_drawing(title, empty_message)

    data = [float(k[value_key]) for k in rows]
    total = sum(data) or 1
    if value_key == 'percentage':
        labels = [f"{short_label(k['name'], 12)} ({float(k[value_key]):.0f}%)" for k in rows]
        legend_pairs = [(wallet_fill_color(k.get('color')), f"{k['name']} — {float(k[value_key]):.1f}%") for k in rows]
    else:
        labels = [f"{short_label(k['name'], 12)} ({(v / total * 100):.0f}%)" for k, v in zip(rows, data)]
        legend_pairs = [(wallet_fill_color(k.get('color')), f"{k['name']} — {money(k[value_key])}") for k in rows]

    drawing = Drawing(480, 230)
    drawing.add(String(0, 212, title, fontName='Helvetica-Bold', fontSize=11, fillColor=colors.HexColor('#172026')))

    pie = Pie()
    pie.x = 55
    pie.y = 28
    pie.width = 155
    pie.height = 155
    pie.data = data
    pie.labels = labels
    pie.slices.strokeWidth = 0.6
    pie.slices.strokeColor = colors.white
    pie.sideLabels = 0
    pie.simpleLabels = 1
    for index, kitty in enumerate(rows):
        pie.slices[index].fillColor = wallet_fill_color(kitty.get('color'))
        pie.slices[index].popout = 2 if index == 0 else 0

    legend = Legend()
    legend.x = 250
    legend.y = 55
    legend.deltay = 16
    legend.dxTextSpace = 8
    legend.columnMaximum = 8
    legend.alignment = 'right'
    legend.fontName = 'Helvetica'
    legend.fontSize = 8
    legend.colorNamePairs = legend_pairs

    drawing.add(pie)
    drawing.add(legend)
    return drawing

def cash_flow_chart(summary):
    income = float(summary.get('income_selected', 0))
    spent = float(summary.get('spent_selected', 0))
    if income <= 0 and spent <= 0:
        return _empty_chart_drawing('Period cash flow', 'No income or spending logged in this period.')

    drawing = Drawing(480, 220)
    drawing.add(String(0, 200, 'Period cash flow — income vs spending', fontName='Helvetica-Bold', fontSize=11, fillColor=colors.HexColor('#172026')))

    chart = VerticalBarChart()
    chart.x = 70
    chart.y = 35
    chart.width = 280
    chart.height = 145
    chart.data = [[income, spent]]
    chart.categoryAxis.categoryNames = ['Income logged', 'Spent in period']
    chart.categoryAxis.labels.angle = 0
    chart.categoryAxis.labels.fontName = 'Helvetica'
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontName = 'Helvetica'
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = colors.HexColor('#0f766e')
    chart.bars[(0, 0)].fillColor = colors.HexColor('#0f766e')
    chart.bars[(0, 1)].fillColor = colors.HexColor('#dc2626')
    chart.barLabels.nudge = 10
    chart.barLabels.fontName = 'Helvetica-Bold'
    chart.barLabels.fontSize = 8

    max_val = max(income, spent, 1)
    chart.valueAxis.valueMax = max_val * 1.15

    drawing.add(chart)
    drawing.add(String(360, 120, f"Net: {('+' if summary.get('net_flow', 0) >= 0 else '−')}{money(abs(summary.get('net_flow', 0)))}", fontName='Helvetica-Bold', fontSize=10, fillColor=colors.HexColor('#172026')))
    return drawing

def wallet_balance_bar_chart(kitties):
    rows = [k for k in kitties if float(k.get('balance', 0)) >= 0]
    if not rows:
        return _empty_chart_drawing('Balance by wallet', 'No wallets configured.')

    drawing = Drawing(480, max(200, 60 + len(rows) * 28))
    drawing.add(String(0, drawing.height - 18, 'Balance by wallet', fontName='Helvetica-Bold', fontSize=11, fillColor=colors.HexColor('#172026')))

    chart = HorizontalBarChart()
    chart.x = 95
    chart.y = 22
    chart.width = 300
    chart.height = max(80, len(rows) * 24)
    chart.data = [[float(k['balance']) for k in rows]]
    chart.categoryAxis.categoryNames = [short_label(k['name'], 14) for k in rows]
    chart.categoryAxis.labels.fontName = 'Helvetica'
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontName = 'Helvetica'
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = colors.HexColor('#0f766e')
    for index, kitty in enumerate(rows):
        chart.bars[(0, index)].fillColor = wallet_fill_color(kitty.get('color'))

    drawing.add(chart)
    return drawing

def coverage_bar_chart(kitties, baseline_label):
    rows = [k for k in kitties if float(k.get('projected_next_month_need', 0)) > 0]
    if not rows:
        return _empty_chart_drawing(
            'Next month coverage',
            'No spending last month to use as a baseline. Log spending over a full month first.'
        )

    rows = sorted(rows, key=lambda k: float(k.get('coverage_pct', 0)))
    drawing = Drawing(480, max(210, 55 + len(rows) * 26))
    drawing.add(String(0, drawing.height - 18, f'Coverage vs last month ({baseline_label})', fontName='Helvetica-Bold', fontSize=10, fillColor=colors.HexColor('#172026')))

    chart = HorizontalBarChart()
    chart.x = 95
    chart.y = 22
    chart.width = 300
    chart.height = max(70, len(rows) * 22)
    chart.data = [[min(100, float(k.get('coverage_pct', 0))) for k in rows]]
    chart.categoryAxis.categoryNames = [short_label(k['name'], 14) for k in rows]
    chart.categoryAxis.labels.fontName = 'Helvetica'
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.valueAxis.labels.fontName = 'Helvetica'
    chart.valueAxis.labels.fontSize = 7
    for index, kitty in enumerate(rows):
        pct = float(kitty.get('coverage_pct', 0))
        chart.bars[(0, index)].fillColor = coverage_bar_color(pct)

    drawing.add(chart)
    drawing.add(String(400, 28, '0%', fontSize=7, fillColor=colors.HexColor('#64727f')))
    drawing.add(String(395, chart.height - 35, '100%', fontSize=7, fillColor=colors.HexColor('#64727f')))
    return drawing

def need_vs_balance_chart(kitties):
    rows = [k for k in kitties if float(k.get('projected_next_month_need', 0)) > 0 or float(k.get('balance', 0)) > 0]
    if not rows:
        return _empty_chart_drawing('Need vs balance', 'No wallet data available.')

    drawing = Drawing(480, max(220, 70 + len(rows) * 30))
    drawing.add(String(0, drawing.height - 18, 'Last month need vs current balance', fontName='Helvetica-Bold', fontSize=11, fillColor=colors.HexColor('#172026')))

    chart = HorizontalBarChart()
    chart.x = 95
    chart.y = 22
    chart.width = 300
    chart.height = max(90, len(rows) * 26)
    chart.data = [
        [float(k.get('projected_next_month_need', 0)) for k in rows],
        [float(k.get('balance', 0)) for k in rows],
    ]
    chart.categoryAxis.categoryNames = [short_label(k['name'], 12) for k in rows]
    chart.categoryAxis.labels.fontName = 'Helvetica'
    chart.categoryAxis.labels.fontSize = 8
    chart.groupSpacing = 8
    chart.barSpacing = 4
    chart.bars[0].fillColor = colors.HexColor('#2563eb')
    chart.bars[1].fillColor = colors.HexColor('#0f766e')
    chart.valueAxis.labels.fontName = 'Helvetica'
    chart.valueAxis.labels.fontSize = 7

    legend = Legend()
    legend.x = 250
    legend.y = drawing.height - 42
    legend.deltax = 70
    legend.fontName = 'Helvetica'
    legend.fontSize = 8
    legend.colorNamePairs = [
        (colors.HexColor('#2563eb'), 'Last month spend'),
        (colors.HexColor('#0f766e'), 'Balance now'),
    ]

    drawing.add(chart)
    drawing.add(legend)
    return drawing

def status_pie_chart(kitties):
    counts = {'healthy': 0, 'low': 0, 'depleted': 0, 'fast': 0}
    for kitty in kitties:
        counts[kitty['status']] = counts.get(kitty['status'], 0) + 1
    labels_keys = [(k, status_label(k)) for k in ['healthy', 'low', 'depleted', 'fast'] if counts.get(k, 0) > 0]
    if not labels_keys:
        return _empty_chart_drawing('Wallet status', 'No wallets to show.')

    data = [counts[k] for k, _ in labels_keys]
    drawing = Drawing(480, 175)
    drawing.add(String(0, 158, 'Wallet status mix', fontName='Helvetica-Bold', fontSize=11, fillColor=colors.HexColor('#172026')))

    pie = Pie()
    pie.x = 65
    pie.y = 18
    pie.width = 120
    pie.height = 120
    pie.data = data
    pie.labels = [f"{label} ({counts[key]})" for key, label in labels_keys]
    pie.slices.strokeWidth = 0.5
    pie.slices.strokeColor = colors.white
    for index, (key, _) in enumerate(labels_keys):
        pie.slices[index].fillColor = status_color(key)

    drawing.add(pie)
    return drawing

def flow_summary_text(summary):
    net = float(summary.get('net_flow', 0))
    income = float(summary.get('income_selected', 0))
    spent = float(summary.get('spent_selected', 0))
    if income <= 0 and spent <= 0:
        return 'No income or spending was logged in the selected period.'
    if net > 0:
        return f'{money(net)} unspent from income in this period (still held across wallets).'
    if net < 0:
        return f'Spending exceeded logged income by {money(abs(net))}. Balances may include earlier income.'
    return 'Income and spending in this period are equal.'

def build_report_data(days=31):
    today = datetime.now()
    period_start = today - timedelta(days=days)
    current_month_start, next_month_start = month_bounds(today.year, today.month)
    previous_start, previous_end = previous_month_bounds(today)

    kitties = Kitty.query.filter_by(user_id=current_user.id).all()

    def spending_between(start, end=None):
        query = db.session.query(
            Kitty.id,
            Kitty.name,
            func.sum(Transaction.amount).label('total')
        ).join(Transaction, Transaction.kitty_id == Kitty.id).filter(
            Transaction.user_id == current_user.id,
            Transaction.type == 'spending',
            Transaction.date >= start
        )
        if end:
            query = query.filter(Transaction.date < end)
        return {row[0]: float(row[2] or 0) for row in query.group_by(Kitty.id, Kitty.name).all()}

    selected_spending = spending_between(period_start)
    current_month_spending = spending_between(current_month_start, next_month_start)
    previous_month_spending = spending_between(previous_start, previous_end)

    income_period_total = db.session.query(func.sum(IncomeSource.amount)).filter(
        IncomeSource.user_id == current_user.id,
        IncomeSource.date_received >= period_start
    ).scalar() or 0

    current_month_income = db.session.query(func.sum(IncomeSource.amount)).filter(
        IncomeSource.user_id == current_user.id,
        IncomeSource.date_received >= current_month_start,
        IncomeSource.date_received < next_month_start
    ).scalar() or 0

    kitty_rows = []
    total_balance = 0
    total_selected_spent = 0
    total_previous_need = 0
    total_gap = 0

    for kitty in kitties:
        spent = selected_spending.get(kitty.id, 0)
        current_spent = current_month_spending.get(kitty.id, 0)
        previous_spent = previous_month_spending.get(kitty.id, 0)
        balance = float(kitty.current_balance or 0)
        available_this_period = balance + spent
        remaining_ratio = (balance / available_this_period) if available_this_period > 0 else 1
        next_month_gap = max(0, previous_spent - balance)

        if balance <= 0:
            status = 'depleted'
        elif remaining_ratio < 0.2:
            status = 'low'
        elif current_spent > previous_spent and previous_spent > 0:
            status = 'fast'
        else:
            status = 'healthy'

        need = previous_spent
        coverage_pct = round(min(100, (balance / need) * 100), 1) if need > 0 else (100.0 if balance > 0 else 0.0)

        kitty_rows.append({
            'id': kitty.id,
            'name': kitty.name,
            'color': kitty.color,
            'percentage': kitty.percentage,
            'balance': balance,
            'spent_selected': spent,
            'spent_current_month': current_spent,
            'spent_previous_month': previous_spent,
            'projected_next_month_need': need,
            'next_month_gap': next_month_gap,
            'remaining_ratio': round(remaining_ratio, 4),
            'coverage_pct': coverage_pct,
            'status': status
        })

        total_balance += balance
        total_selected_spent += spent
        total_previous_need += previous_spent
        total_gap += next_month_gap

    if total_selected_spent > 0:
        for row in kitty_rows:
            row['spend_share_pct'] = round((row['spent_selected'] / total_selected_spent) * 100, 1)
    else:
        for row in kitty_rows:
            row['spend_share_pct'] = 0.0

    kitty_rows.sort(key=lambda row: row['spent_selected'], reverse=True)

    biggest_spend = max(kitty_rows, key=lambda row: row['spent_selected'], default=None)
    depleted = [row for row in kitty_rows if row['status'] == 'depleted']
    low = [row for row in kitty_rows if row['status'] in ['depleted', 'low']]
    income_selected = float(income_period_total)
    net_flow = income_selected - total_selected_spent
    overall_coverage = round(min(100, (total_balance / total_previous_need) * 100), 1) if total_previous_need > 0 else (100.0 if total_balance > 0 else 0.0)

    period_start_label = fmt_period_date(period_start.date().isoformat())
    period_end_label = fmt_period_date(today.date().isoformat())
    baseline_start_label = fmt_period_date(previous_start.date().isoformat())
    baseline_end_label = fmt_period_date((previous_end - timedelta(days=1)).date().isoformat())

    insights = []
    if not kitties:
        insights.append({
            'level': 'info',
            'title': 'No wallets yet',
            'message': 'Create wallets on Home and log income to unlock spending insights.'
        })
    else:
        if biggest_spend and biggest_spend['spent_selected'] > 0:
            share = biggest_spend.get('spend_share_pct', 0)
            insights.append({
                'level': 'info',
                'title': f"Top spend: {biggest_spend['name']}",
                'message': f"{money(biggest_spend['spent_selected'])} in this period ({share:.0f}% of your spending)."
            })
        if income_selected > 0 and total_selected_spent > income_selected:
            insights.append({
                'level': 'warn',
                'title': 'Spending above income',
                'message': f"You spent {money(total_selected_spent - income_selected)} more than you logged as income in this period."
            })
        elif net_flow > 0:
            insights.append({
                'level': 'success',
                'title': 'Positive period',
                'message': f"{money(net_flow)} more income than spending logged in this period."
            })
        if low:
            names = ', '.join(row['name'] for row in low[:3])
            extra = f" (+{len(low) - 3} more)" if len(low) > 3 else ''
            insights.append({
                'level': 'warn',
                'title': f"{len(low)} wallet{'s' if len(low) != 1 else ''} need attention",
                'message': f"{names}{extra} — balance is low or empty."
            })
        if total_gap > 0:
            insights.append({
                'level': 'warn',
                'title': 'Next month shortfall',
                'message': f"Last month's spending was {money(total_previous_need)}. Current balances leave a {money(total_gap)} gap."
            })
        elif total_previous_need > 0:
            insights.append({
                'level': 'success',
                'title': 'Next month covered',
                'message': f"Your {money(total_balance)} across wallets can cover last month's {money(total_previous_need)} spend pattern."
            })

    return {
        'profile': {
            'name': current_user.name or current_user.username,
            'phone': current_user.phone or 'Not set',
            'username': current_user.username,
        },
        'period': {
            'days': days,
            'start': period_start.date().isoformat(),
            'end': today.date().isoformat(),
            'label': f"{period_start_label} – {period_end_label}",
            'previous_month_start': previous_start.date().isoformat(),
            'previous_month_end': (previous_end - timedelta(days=1)).date().isoformat(),
            'baseline_label': f"{baseline_start_label} – {baseline_end_label}",
            'current_month_start': current_month_start.date().isoformat(),
            'generated_at': today.strftime('%Y-%m-%d %H:%M')
        },
        'summary': {
            'total_balance': total_balance,
            'spent_selected': total_selected_spent,
            'income_selected': income_selected,
            'current_month_income': float(current_month_income),
            'net_flow': net_flow,
            'projected_next_month_need': total_previous_need,
            'next_month_gap': total_gap,
            'overall_coverage_pct': overall_coverage,
            'kitty_count': len(kitties),
            'depleted_count': len(depleted),
            'low_count': len(low)
        },
        'kitties': kitty_rows,
        'insights': insights
    }

WALLET_TEMPLATES = {
    'student': [
        {'name': 'Food', 'percentage': 25, 'color': '#0f766e', 'monthly_cap': 5000},
        {'name': 'Transport', 'percentage': 15, 'color': '#2563eb', 'monthly_cap': 3000},
        {'name': 'Airtime & data', 'percentage': 10, 'color': '#6d28d9', 'monthly_cap': 1500},
        {'name': 'School', 'percentage': 20, 'color': '#d97706', 'monthly_cap': 4000},
        {'name': 'Savings', 'percentage': 20, 'color': '#059669', 'monthly_cap': None},
        {'name': 'Fun', 'percentage': 10, 'color': '#ec4899', 'monthly_cap': 2000},
    ],
    'hustle': [
        {'name': 'Bills', 'percentage': 30, 'color': '#0f766e', 'monthly_cap': 8000},
        {'name': 'Food', 'percentage': 20, 'color': '#2563eb', 'monthly_cap': 5000},
        {'name': 'Transport', 'percentage': 15, 'color': '#6d28d9', 'monthly_cap': 3000},
        {'name': 'Business costs', 'percentage': 15, 'color': '#d97706', 'monthly_cap': 4000},
        {'name': 'Savings', 'percentage': 20, 'color': '#059669', 'monthly_cap': None},
    ],
    'employed': [
        {'name': 'Rent', 'percentage': 35, 'color': '#0f766e', 'monthly_cap': 15000},
        {'name': 'Food', 'percentage': 20, 'color': '#2563eb', 'monthly_cap': 8000},
        {'name': 'Transport', 'percentage': 10, 'color': '#6d28d9', 'monthly_cap': 4000},
        {'name': 'Utilities', 'percentage': 10, 'color': '#d97706', 'monthly_cap': 3000},
        {'name': 'Savings', 'percentage': 15, 'color': '#059669', 'monthly_cap': None},
        {'name': 'Personal', 'percentage': 10, 'color': '#ec4899', 'monthly_cap': 5000},
    ],
}

def migrate_database():
    inspector = inspect(db.engine)
    if not inspector.has_table('user'):
        return

    columns = {column['name'] for column in inspector.get_columns('user')}
    with db.engine.begin() as connection:
        if 'name' not in columns:
            connection.exec_driver_sql('ALTER TABLE user ADD COLUMN name VARCHAR(120)')
        if 'phone' not in columns:
            connection.exec_driver_sql('ALTER TABLE user ADD COLUMN phone VARCHAR(30)')
        if 'onboarding_done' not in columns:
            connection.exec_driver_sql('ALTER TABLE user ADD COLUMN onboarding_done BOOLEAN DEFAULT 0')

    if inspector.has_table('kitty'):
        kitty_columns = {column['name'] for column in inspector.get_columns('kitty')}
        with db.engine.begin() as connection:
            if 'monthly_cap' not in kitty_columns:
                connection.exec_driver_sql('ALTER TABLE kitty ADD COLUMN monthly_cap FLOAT')

    if inspector.has_table('transaction'):
        tx_columns = {column['name'] for column in inspector.get_columns('transaction')}
        with db.engine.begin() as connection:
            if 'related_kitty_id' not in tx_columns:
                connection.exec_driver_sql('ALTER TABLE "transaction" ADD COLUMN related_kitty_id INTEGER')

with app.app_context():
    db.create_all()
    migrate_database()
    # Create default user if none exists
    if not User.query.first():
        default_user = User(name='Demo User', phone='254700000000', username='user', password_hash=generate_password_hash('password123'))
        db.session.add(default_user)
        db.session.commit()
    demo_user = User.query.filter_by(username='user').first()
    if demo_user and not demo_user.phone:
        demo_user.name = demo_user.name or 'Demo User'
        demo_user.phone = '254700000000'
        db.session.commit()
    for user in User.query.all():
        if Kitty.query.filter_by(user_id=user.id).count() > 0:
            user.onboarding_done = True
    db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def kitty_spent_this_month(kitty_id, user_id):
    today = datetime.now()
    start, end = month_bounds(today.year, today.month)
    total = db.session.query(func.sum(Transaction.amount)).filter(
        Transaction.kitty_id == kitty_id,
        Transaction.user_id == user_id,
        Transaction.type == 'spending',
        Transaction.date >= start,
        Transaction.date < end,
    ).scalar()
    return float(total or 0)

def user_needs_onboarding():
    if not current_user.is_authenticated:
        return False
    if current_user.onboarding_done:
        return False
    return Kitty.query.filter_by(user_id=current_user.id).count() == 0

def serialize_kitty(kitty):
    spent_month = kitty_spent_this_month(kitty.id, kitty.user_id)
    cap = kitty.monthly_cap
    return {
        'id': kitty.id,
        'name': kitty.name,
        'percentage': kitty.percentage,
        'current_balance': kitty.current_balance,
        'monthly_cap': cap,
        'spent_this_month': spent_month,
        'cap_remaining': (cap - spent_month) if cap else None,
        'color': kitty.color,
    }

# Routes
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_id = request.form['username'].strip()
        phone = normalize_phone(login_id)
        user = User.query.filter((User.username == login_id) | (User.phone == phone)).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            if not user.onboarding_done and Kitty.query.filter_by(user_id=user.id).count() == 0:
                return redirect(url_for('onboarding'))
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = normalize_phone(request.form.get('phone', ''))
        password = request.form.get('password', '')

        if not name or not phone or not password:
            flash('Name, phone number, and password are required')
            return render_template('login.html', mode='register')
        if len(phone) < 9:
            flash('Enter a valid phone number')
            return render_template('login.html', mode='register')
        if len(password) < 6:
            flash('Use at least 6 characters for your password')
            return render_template('login.html', mode='register')
        if User.query.filter((User.phone == phone) | (User.username == phone)).first():
            flash('An account with that phone number already exists')
            return render_template('login.html', mode='register')

        user = User(
            name=name,
            phone=phone,
            username=phone,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('onboarding'))

    return render_template('login.html', mode='register')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/onboarding')
@login_required
def onboarding():
    if not user_needs_onboarding():
        return redirect(url_for('dashboard'))
    return render_template('onboarding.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if user_needs_onboarding():
        return redirect(url_for('onboarding'))
    return render_template('dashboard.html')

@app.route('/activity')
@login_required
def activity_page():
    return render_template('activity.html', active_nav='activity')

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = normalize_phone(request.form.get('phone', ''))
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not name or not phone or not username:
            flash('Name, phone number, and username are required')
            return render_template('account.html')
        if len(phone) < 9:
            flash('Enter a valid phone number')
            return render_template('account.html')

        existing_phone = User.query.filter(User.phone == phone, User.id != current_user.id).first()
        existing_username = User.query.filter(User.username == username, User.id != current_user.id).first()
        if existing_phone:
            flash('That phone number is already used by another account')
            return render_template('account.html')
        if existing_username:
            flash('That username is already used by another account')
            return render_template('account.html')
        if password and len(password) < 6:
            flash('Use at least 6 characters for your new password')
            return render_template('account.html')

        current_user.name = name
        current_user.phone = phone
        current_user.username = username
        if password:
            current_user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash('Account updated')
        return redirect(url_for('account'))

    return render_template('account.html')

# API endpoints
@app.route('/api/onboarding/setup', methods=['POST'])
@login_required
def onboarding_setup():
    data = request.json or {}
    template_key = data.get('template')
    if template_key not in WALLET_TEMPLATES:
        return jsonify({'error': 'Choose a valid template'}), 400
    if Kitty.query.filter_by(user_id=current_user.id).count() > 0:
        return jsonify({'error': 'You already have wallets. Remove them first or skip onboarding.'}), 400

    for item in WALLET_TEMPLATES[template_key]:
        db.session.add(Kitty(
            user_id=current_user.id,
            name=item['name'],
            percentage=item['percentage'],
            color=item['color'],
            monthly_cap=item.get('monthly_cap'),
        ))
    current_user.onboarding_done = True
    db.session.commit()
    return jsonify({'message': 'Wallets created', 'template': template_key}), 201

@app.route('/api/onboarding/skip', methods=['POST'])
@login_required
def onboarding_skip():
    current_user.onboarding_done = True
    db.session.commit()
    return jsonify({'message': 'Skipped'})

@app.route('/api/kitties')
@login_required
def get_kitties():
    kitties = Kitty.query.filter_by(user_id=current_user.id).all()
    return jsonify([serialize_kitty(k) for k in kitties])

@app.route('/api/kitties', methods=['POST'])
@login_required
def add_kitty():
    data = request.json
    percentage = float(data.get('percentage', 0))
    if not data.get('name') or percentage <= 0:
        return jsonify({'error': 'Kitty name and a positive percentage are required'}), 400

    # Validate total percentage <= 100
    total = sum(k.percentage for k in Kitty.query.filter_by(user_id=current_user.id).all())
    if total + percentage > 100:
        return jsonify({'error': 'Total percentages cannot exceed 100%'}), 400
    
    cap = data.get('monthly_cap')
    kitty = Kitty(
        user_id=current_user.id,
        name=data['name'],
        percentage=percentage,
        color=data.get('color', '#6366f1'),
        monthly_cap=float(cap) if cap not in (None, '') else None,
    )
    db.session.add(kitty)
    db.session.commit()
    return jsonify({'message': 'Kitty added'}), 201

@app.route('/api/kitties/<int:kitty_id>', methods=['PUT'])
@login_required
def update_kitty(kitty_id):
    kitty = Kitty.query.get_or_404(kitty_id)
    if kitty.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    percentage = float(data.get('percentage', 0))
    if not data.get('name') or percentage <= 0:
        return jsonify({'error': 'Kitty name and a positive percentage are required'}), 400

    other_total = sum(
        k.percentage for k in Kitty.query.filter_by(user_id=current_user.id).all()
        if k.id != kitty.id
    )
    if other_total + percentage > 100:
        return jsonify({'error': 'Total percentages cannot exceed 100%'}), 400

    kitty.name = data['name']
    kitty.percentage = percentage
    kitty.color = data.get('color', kitty.color)
    if 'monthly_cap' in data:
        cap = data.get('monthly_cap')
        kitty.monthly_cap = float(cap) if cap not in (None, '') else None
    db.session.commit()
    return jsonify({'message': 'Kitty updated'})

@app.route('/api/kitties/<int:kitty_id>', methods=['DELETE'])
@login_required
def delete_kitty(kitty_id):
    kitty = Kitty.query.get_or_404(kitty_id)
    if kitty.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(kitty)
    db.session.commit()
    return jsonify({'message': 'Deleted'})

@app.route('/api/income')
@login_required
def get_income():
    incomes = IncomeSource.query.filter_by(user_id=current_user.id).order_by(IncomeSource.date_received.desc()).all()
    return jsonify([{
        'id': i.id,
        'name': i.name,
        'amount': i.amount,
        'date_received': i.date_received.isoformat(),
        'notes': i.notes
    } for i in incomes])

@app.route('/api/income', methods=['POST'])
@login_required
def add_income():
    data = request.json
    amount = float(data.get('amount', 0))
    if not data.get('name') or amount <= 0:
        return jsonify({'error': 'Income source and a positive amount are required'}), 400

    kitties = Kitty.query.filter_by(user_id=current_user.id).all()
    total_percentage = sum(k.percentage for k in kitties)
    if not kitties:
        return jsonify({'error': 'Create kitties before adding income so the money has a plan'}), 400
    if round(total_percentage, 2) != 100:
        return jsonify({'error': f'Kitty percentages must total 100% before adding income. Current total: {total_percentage:.1f}%'}), 400

    income = IncomeSource(
        user_id=current_user.id,
        name=data['name'],
        amount=amount,
        notes=data.get('notes', '')
    )
    db.session.add(income)
    db.session.commit()
    
    # Auto-allocate to kitties based on percentages
    for kitty in kitties:
        allocation = (kitty.percentage / 100) * amount
        kitty.current_balance += allocation
    db.session.commit()

    breakdown = [
        {'name': k.name, 'amount': round((k.percentage / 100) * amount, 2), 'color': k.color}
        for k in kitties
    ]
    return jsonify({
        'message': 'Income added and allocated',
        'breakdown': breakdown,
        'total': amount,
    }), 201

@app.route('/api/transfer', methods=['POST'])
@login_required
def transfer_between_kitties():
    data = request.json or {}
    amount = float(data.get('amount', 0))
    from_id = data.get('from_kitty_id')
    to_id = data.get('to_kitty_id')
    note = (data.get('note') or '').strip()

    if amount <= 0:
        return jsonify({'error': 'Enter a positive amount'}), 400
    if not from_id or not to_id or from_id == to_id:
        return jsonify({'error': 'Choose two different wallets'}), 400

    from_kitty = Kitty.query.get_or_404(from_id)
    to_kitty = Kitty.query.get_or_404(to_id)
    if from_kitty.user_id != current_user.id or to_kitty.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    if from_kitty.current_balance < amount:
        return jsonify({'error': f'Not enough in {from_kitty.name}. Available: {money(from_kitty.current_balance)}'}), 400

    label = note or f'To {to_kitty.name}'
    from_kitty.current_balance -= amount
    to_kitty.current_balance += amount
    db.session.add(Transaction(
        user_id=current_user.id,
        kitty_id=from_kitty.id,
        related_kitty_id=to_kitty.id,
        amount=amount,
        description=label,
        type='transfer_out',
    ))
    db.session.add(Transaction(
        user_id=current_user.id,
        kitty_id=to_kitty.id,
        related_kitty_id=from_kitty.id,
        amount=amount,
        description=note or f'From {from_kitty.name}',
        type='transfer_in',
    ))
    db.session.commit()
    return jsonify({
        'message': f'Moved {money(amount)} to {to_kitty.name}',
        'from_balance': from_kitty.current_balance,
        'to_balance': to_kitty.current_balance,
    })

@app.route('/api/spend', methods=['POST'])
@login_required
def spend():
    data = request.json
    amount = float(data.get('amount', 0))
    if amount <= 0:
        return jsonify({'error': 'Enter a positive spending amount'}), 400

    kitty = Kitty.query.get_or_404(data['kitty_id'])
    
    if kitty.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if kitty.current_balance < amount:
        return jsonify({'error': f'Insufficient funds in {kitty.name}. Available: {kitty.current_balance}'}), 400

    if kitty.monthly_cap:
        spent = kitty_spent_this_month(kitty.id, current_user.id)
        if spent + amount > kitty.monthly_cap:
            remaining = max(0, kitty.monthly_cap - spent)
            return jsonify({
                'error': f'{kitty.name} monthly cap is {money(kitty.monthly_cap)}. Only {money(remaining)} left this month.'
            }), 400

    kitty.current_balance -= amount
    transaction = Transaction(
        user_id=current_user.id,
        kitty_id=kitty.id,
        amount=amount,
        description=data.get('description', ''),
        type='spending'
    )
    db.session.add(transaction)
    db.session.commit()
    
    return jsonify({'message': 'Spending recorded', 'new_balance': kitty.current_balance})

def serialize_transaction(t):
    related = Kitty.query.get(t.related_kitty_id) if t.related_kitty_id else None
    return {
        'id': t.id,
        'kitty_id': t.kitty_id,
        'kitty_name': t.kitty.name,
        'related_kitty_name': related.name if related else None,
        'amount': t.amount,
        'description': t.description,
        'date': t.date.isoformat(),
        'type': t.type,
    }

@app.route('/api/transactions')
@login_required
def get_transactions():
    days = request.args.get('days', type=int)
    kitty_id = request.args.get('kitty_id', type=int)
    tx_type = request.args.get('type', '').strip()

    query = Transaction.query.filter_by(user_id=current_user.id)
    if days:
        query = query.filter(Transaction.date >= datetime.now() - timedelta(days=days))
    if kitty_id:
        query = query.filter(Transaction.kitty_id == kitty_id)
    if tx_type:
        query = query.filter(Transaction.type == tx_type)

    limit = min(request.args.get('limit', 200, type=int), 500)
    transactions = query.order_by(Transaction.date.desc()).limit(limit).all()
    return jsonify([serialize_transaction(t) for t in transactions])

@app.route('/api/transactions/<int:tx_id>', methods=['PUT'])
@login_required
def update_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    if tx.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    if tx.type != 'spending':
        return jsonify({'error': 'Only expenses can be edited'}), 400

    data = request.json or {}
    kitty = Kitty.query.get_or_404(data.get('kitty_id', tx.kitty_id))
    if kitty.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    new_amount = float(data.get('amount', tx.amount))
    if new_amount <= 0:
        return jsonify({'error': 'Amount must be positive'}), 400

    old_kitty = tx.kitty
    old_amount = tx.amount
    old_kitty.current_balance += old_amount

    if kitty.current_balance < new_amount:
        old_kitty.current_balance -= old_amount
        return jsonify({'error': f'Insufficient funds in {kitty.name}'}), 400

    if kitty.monthly_cap and kitty.id != old_kitty.id:
        spent = kitty_spent_this_month(kitty.id, current_user.id) - (old_amount if old_kitty.id == kitty.id else 0)
        if spent + new_amount > kitty.monthly_cap:
            old_kitty.current_balance -= old_amount
            return jsonify({'error': f'Monthly cap for {kitty.name} exceeded'}), 400
    elif kitty.monthly_cap and kitty.id == old_kitty.id:
        spent = kitty_spent_this_month(kitty.id, current_user.id) - old_amount
        if spent + new_amount > kitty.monthly_cap:
            old_kitty.current_balance -= old_amount
            return jsonify({'error': f'Monthly cap for {kitty.name} exceeded'}), 400

    kitty.current_balance -= new_amount
    tx.kitty_id = kitty.id
    tx.amount = new_amount
    tx.description = data.get('description', tx.description)
    db.session.commit()
    return jsonify({'message': 'Expense updated', 'transaction': serialize_transaction(tx)})

@app.route('/api/transactions/<int:tx_id>', methods=['DELETE'])
@login_required
def delete_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    if tx.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    if tx.type == 'spending':
        tx.kitty.current_balance += tx.amount
        db.session.delete(tx)
    elif tx.type in ('transfer_out', 'transfer_in'):
        pair_type = 'transfer_in' if tx.type == 'transfer_out' else 'transfer_out'
        pair = Transaction.query.filter(
            Transaction.user_id == current_user.id,
            Transaction.type == pair_type,
            Transaction.kitty_id == tx.related_kitty_id,
            Transaction.related_kitty_id == tx.kitty_id,
            Transaction.amount == tx.amount,
        ).order_by(Transaction.date.desc()).first()
        if tx.type == 'transfer_out':
            tx.kitty.current_balance += tx.amount
            if pair:
                pair.kitty.current_balance -= tx.amount
                db.session.delete(pair)
        else:
            tx.kitty.current_balance -= tx.amount
            if pair:
                pair.kitty.current_balance += tx.amount
                db.session.delete(pair)
        db.session.delete(tx)
    else:
        return jsonify({'error': 'Cannot delete this entry type here'}), 400

    db.session.commit()
    return jsonify({'message': 'Removed'})

@app.route('/api/income/<int:income_id>', methods=['DELETE'])
@login_required
def delete_income(income_id):
    income = IncomeSource.query.get_or_404(income_id)
    if income.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    kitties = Kitty.query.filter_by(user_id=current_user.id).all()
    total_pct = sum(k.percentage for k in kitties) or 100
    for kitty in kitties:
        kitty.current_balance -= (kitty.percentage / total_pct) * income.amount
        kitty.current_balance = max(0, kitty.current_balance)
    db.session.delete(income)
    db.session.commit()
    return jsonify({'message': 'Income removed and allocation reversed'})

@app.route('/api/reports/spending')
@login_required
def spending_report():
    days = request.args.get('days', 30, type=int)
    start_date = datetime.now() - timedelta(days=days)
    
    results = db.session.query(
        Kitty.name,
        func.sum(Transaction.amount).label('total')
    ).join(Transaction, Transaction.kitty_id == Kitty.id).filter(
        Transaction.user_id == current_user.id,
        Transaction.date >= start_date,
        Transaction.type == 'spending'
    ).group_by(Kitty.name).all()
    
    return jsonify([{'kitty': r[0], 'total': float(r[1] or 0)} for r in results])

@app.route('/api/reports/insights')
@login_required
def report_insights():
    days = request.args.get('days', 31, type=int)
    return jsonify(build_report_data(days))

@app.route('/reports/pdf')
@login_required
def reports_pdf():
    days = request.args.get('days', 31, type=int)
    sections = request.args.getlist('sections') or ['summary', 'kitty_health', 'projection', 'insights']
    allowed_sections = {'summary', 'kitty_health', 'projection', 'insights'}
    sections = [section for section in sections if section in allowed_sections]
    if not sections:
        sections = ['summary']

    data = build_report_data(days)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    styles['Title'].fontSize = 20
    styles['Title'].textColor = colors.HexColor('#1a2332')
    styles['Title'].spaceAfter = 4
    styles['Heading2'].fontSize = 13
    styles['Heading2'].textColor = colors.HexColor('#0f766e')
    styles['Heading2'].spaceBefore = 10
    styles['Heading2'].spaceAfter = 8
    normal = ParagraphStyle(
        'ReportNormal',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#1a2332'),
    )
    muted = ParagraphStyle(
        'ReportMuted',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#5c6b7a'),
    )
    story = []

    profile = data['profile']
    period = data['period']
    summary = data['summary']
    kitties = data['kitties']

    story.append(Paragraph('PesaPlan — Spending Report', styles['Title']))
    story.append(Paragraph(f"<b>Period:</b> {period.get('label', period['start'] + ' – ' + period['end'])}", muted))
    story.append(Paragraph(
        f"Generated {period['generated_at']} · Baseline for coverage: {period.get('baseline_label', '')}",
        muted
    ))
    story.append(Spacer(1, 12))

    meta_table = Table([
        ['Prepared for', profile['name']],
        ['Phone', profile['phone']],
        ['Username', profile['username']],
        ['Wallets tracked', str(summary['kitty_count'])],
    ], colWidths=[120, 370])
    meta_table.setStyle(pdf_label_value_table_style())
    story.append(meta_table)
    story.append(Spacer(1, 16))

    if 'summary' in sections:
        story.append(Paragraph('At a glance', styles['Heading2']))
        story.append(summary_cards(summary))
        story.append(Spacer(1, 14))
        story.append(cash_flow_chart(summary))
        story.append(Spacer(1, 8))
        story.append(Paragraph(flow_summary_text(summary), normal))
        story.append(Spacer(1, 14))
        story.append(wallet_pie_chart(
            kitties, 'balance',
            'How your money is split across wallets (current balances)',
            'No balances in wallets yet.'
        ))
        story.append(Spacer(1, 14))
        story.append(wallet_pie_chart(
            kitties, 'percentage',
            'Planned income split (% allocation per wallet)',
            'Set wallet percentages on Home.'
        ))
        story.append(Spacer(1, 10))
        forward_rows = [
            ['Last month spend (baseline)', money(summary['projected_next_month_need'])],
            ['Current balances across wallets', money(summary['total_balance'])],
            ['Overall coverage', f"{summary['overall_coverage_pct']:.0f}%" if summary['projected_next_month_need'] > 0 else '—'],
            ['Shortfall if pattern repeats', money(summary['next_month_gap'])],
            ['Wallets needing attention', str(summary['low_count'])],
        ]
        story.append(Paragraph('Forward look (vs last full month)', styles['Heading2']))
        forward_table = Table(forward_rows, colWidths=[220, 270])
        forward_table.setStyle(pdf_label_value_table_style())
        story.append(forward_table)
        story.append(Spacer(1, 14))

    if 'kitty_health' in sections:
        story.append(PageBreak())
        story.append(Paragraph('Spending &amp; wallets', styles['Heading2']))
        has_spending = any(float(k.get('spent_selected', 0)) > 0 for k in kitties)
        if has_spending:
            story.append(Paragraph('Where your spending went this period.', muted))
            story.append(wallet_pie_chart(
                kitties, 'spent_selected',
                'Spending breakdown (this period)',
                'No spending in this period.'
            ))
        else:
            story.append(Paragraph(
                'No spending logged in this period — charts show current balances and planned splits instead.',
                muted
            ))
            story.append(wallet_pie_chart(
                kitties, 'balance',
                'Current balance by wallet',
                'No wallet balances yet.'
            ))
        story.append(Spacer(1, 12))
        story.append(wallet_balance_bar_chart(kitties))
        story.append(Spacer(1, 10))
        if kitties:
            story.append(status_pie_chart(kitties))
            story.append(Spacer(1, 10))
        wallet_rows = [['Wallet', 'Status', 'Period spend', 'Balance', 'Share', 'Covers next mo.']]
        for kitty in kitties:
            share = f"{kitty['spend_share_pct']:.0f}%" if kitty['spent_selected'] > 0 else '—'
            if kitty['projected_next_month_need'] > 0:
                cover = f"{kitty['coverage_pct']:.0f}%"
                if kitty['next_month_gap'] > 0:
                    cover += f" (short {money(kitty['next_month_gap'])})"
            elif kitty['balance'] > 0:
                cover = 'No baseline'
            else:
                cover = '—'
            wallet_rows.append([
                kitty['name'],
                status_label(kitty['status']),
                money(kitty['spent_selected']) if kitty['spent_selected'] > 0 else '—',
                money(kitty['balance']),
                share,
                cover,
            ])
        if len(wallet_rows) == 1:
            wallet_rows.append(['No wallets yet', '—', '—', '—', '—', '—'])
        wallet_table = Table(wallet_rows, colWidths=[95, 72, 72, 72, 42, 107])
        wallet_table.setStyle(pdf_header_table_style())
        story.append(wallet_table)
        story.append(Spacer(1, 14))

    if 'projection' in sections:
        story.append(PageBreak())
        story.append(Paragraph('Next month outlook', styles['Heading2']))
        story.append(Paragraph(
            f"Coverage compares each wallet's balance to what you spent last month ({period.get('baseline_label', '')}).",
            muted
        ))
        story.append(coverage_bar_chart(kitties, period.get('baseline_label', '')))
        story.append(Spacer(1, 12))
        has_baseline = any(float(k.get('projected_next_month_need', 0)) > 0 for k in kitties)
        if has_baseline:
            story.append(need_vs_balance_chart(kitties))
            story.append(Spacer(1, 10))
        else:
            story.append(Paragraph(
                'Once you have a full month of spending history, need-vs-balance and coverage charts will populate here.',
                muted
            ))
            story.append(Spacer(1, 8))
        story.append(Spacer(1, 6))
        cover_rows = [['Wallet', 'Last month spent', 'Balance now', 'Coverage', 'Shortfall']]
        for kitty in kitties:
            cover_rows.append([
                kitty['name'],
                money(kitty['projected_next_month_need']) if kitty['projected_next_month_need'] > 0 else '—',
                money(kitty['balance']),
                f"{kitty['coverage_pct']:.0f}%" if kitty['projected_next_month_need'] > 0 else '—',
                money(kitty['next_month_gap']) if kitty['next_month_gap'] > 0 else '—',
            ])
        if len(cover_rows) == 1:
            cover_rows.append(['No wallets yet', '—', '—', '—', '—'])
        cover_table = Table(cover_rows, colWidths=[100, 95, 85, 60, 90])
        cover_table.setStyle(pdf_header_table_style('#2563eb'))
        story.append(cover_table)
        story.append(Spacer(1, 14))

    if 'insights' in sections:
        story.append(Paragraph('Alerts &amp; takeaways', styles['Heading2']))
        if data['insights']:
            for insight in data['insights']:
                if isinstance(insight, dict):
                    level = insight.get('level', 'info').upper()
                    title = insight.get('title', '')
                    message = insight.get('message', '')
                    story.append(Paragraph(f"<b>[{level}] {title}</b>", normal))
                    story.append(Paragraph(message, muted))
                else:
                    story.append(Paragraph(f"• {insight}", normal))
                story.append(Spacer(1, 6))
        else:
            story.append(Paragraph(
                'Log income and spending to generate personalized takeaways for this report.',
                muted
            ))

    doc.build(story)
    buffer.seek(0)
    filename = f"pesaplan-report-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)

@app.route('/api/reports/income_over_time')
@login_required
def income_over_time():
    days = request.args.get('days', 30, type=int)
    start_date = datetime.now() - timedelta(days=days)
    
    results = db.session.query(
        func.date(IncomeSource.date_received).label('date'),
        func.sum(IncomeSource.amount).label('total')
    ).filter(
        IncomeSource.user_id == current_user.id,
        IncomeSource.date_received >= start_date
    ).group_by(func.date(IncomeSource.date_received)).all()
    
    return jsonify([{'date': r[0], 'total': float(r[1])} for r in results])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
