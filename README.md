# Finance Manager

A comprehensive web-based financial management application built with Flask and SQLite. Track expenses, manage accounts, view activity reports, and gain insights into your spending habits.

## Features

- **Dashboard**: Overview of your financial status and recent activity
- **Account Management**: Create and manage multiple accounts
- **Activity Tracking**: Log and track all financial transactions
- **Reports**: Generate detailed financial reports and analytics
- **User Authentication**: Secure login system
- **Onboarding**: Interactive setup wizard for new users

## Tech Stack

- **Backend**: Python 3 with Flask web framework
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, JavaScript
- **Containerization**: Docker & Docker Compose

## Installation

### Prerequisites
- Python 3.7+
- pip package manager
- Docker (optional, for containerized deployment)

### Local Setup

1. Clone the repository:
```bash
git clone https://github.com/marlonbino/finance-manager.git
cd finance-manager
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

### Docker Setup

Build and run with Docker Compose:
```bash
docker-compose up --build
```

## Project Structure

```
finance-manager/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── dockerfile            # Docker container configuration
├── docker-compose.yml    # Docker Compose setup
├── data/                 # Database files
├── static/
│   ├── css/             # Stylesheets
│   └── js/              # Client-side scripts
└── templates/           # HTML templates
    ├── base.html
    ├── dashboard.html
    ├── login.html
    ├── account.html
    ├── activity.html
    ├── onboarding.html
    └── reports.html
```

## Usage

### Getting Started
1. Sign up or log in to your account
2. Complete the onboarding wizard
3. Add your financial accounts
4. Start tracking transactions
5. View reports and analytics

## API Endpoints

- `GET /` - Dashboard
- `POST /login` - User authentication
- `GET /accounts` - Account management
- `GET /activity` - Transaction activity
- `GET /reports` - Financial reports

## Contributing

Feel free to fork this project and submit pull requests for any improvements.

## License

This project is open source and available under the MIT License.

## Author

**Marlon** - [@marlonbino](https://github.com/marlonbino)

## Support

For issues and feature requests, please open an issue on GitHub.

---

Built with ❤️ by Marlon
