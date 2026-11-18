# WorkFlow

WorkFlow is a Django team task tracker. Teams can organize tasks into projects with start and due dates, see project-specific completion and member workload charts, use a calendar, and export task reports as CSV. Tasks support comments, activity history, and protected file attachments. Members can add profile pictures and post progress updates. Managers create and revoke reusable invite codes and manage membership. Data and live updates are limited to each team.

The shared WorkFlow logo mark is in `tasks/static/tasks/workflow-mark.svg` and appears in the sidebar, sign-in, registration, and team creation pages.

## Run on your computer (current SQLite setup)

Open PowerShell in this folder, then run:

```powershell
.\venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ in a browser. The development server stays available only while that terminal is running. After installing new dependencies or pulling code, activate the environment and install them with `pip install -r requirements.txt`. Run migrations after model changes.

New accounts verify their email with a 6-digit code valid for 5 minutes, then create a username and password. Returning members sign in with username and password; email is not requested on ordinary logins. After signing in, the browser session lasts up to 30 days of inactivity and is renewed while the user keeps using WorkFlow, so reopening the app does not ask them to sign in again. During local development, Django prints signup verification emails in the terminal running `runserver`; it does not deliver to a real inbox by default. To send actual email, set SMTP environment variables before starting Django: `EMAIL_HOST`, `EMAIL_PORT` (usually 587), `EMAIL_USE_TLS` (`True`), `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `DEFAULT_FROM_EMAIL`. Keep the password private and do not commit it to the project.

### Send signup codes to users' email addresses

WorkFlow sends each signup code to the address entered by that new user. The SMTP sender account is a separate account configured once by the WorkFlow owner; team members do not need to configure SMTP or enable 2-Step Verification to use WorkFlow. For public deployment, configure the SMTP variables in the hosting provider's private environment settings. Use a transactional email provider and a verified sender/domain for a real client deployment. Do not put sender credentials in browser code or commit them to the repository.

1. If using Gmail as the sender for local testing, turn on 2-Step Verification for that one Google sender account, then create a Google App Password for WorkFlow. This requirement applies only to the sender account, never to users receiving sign-in codes. Google requires 2-Step Verification for App Passwords and recommends using them only when a safer sign-in option is unavailable. See [Google's App Password instructions](https://support.google.com/accounts/answer/185833).
2. In PowerShell, from the WorkFlow project folder, copy the example settings: `Copy-Item .env.example .env`.
3. Open `.env` in VS Code and replace the sender address and `EMAIL_HOST_PASSWORD` with your Gmail address and App Password. Do not paste that password into chat or commit `.env` to Git.
4. Install the project requirements once: `pip install -r requirements.txt`.
5. Restart Django. On the signup page, request a code for an email that is not already registered. The verification code should arrive in that inbox; check Spam if you don't see it.

If Gmail rejects the connection, confirm 2-Step Verification is on and that `EMAIL_HOST_PASSWORD` contains the App Password, not your normal Gmail password. After changing your Google account password, Google revokes its App Passwords, so create a new one.

Browser/desktop push alerts require HTTPS (localhost is allowed for local development), browser notification permission, and VAPID public/private keys configured as `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and `VAPID_SUBJECT`. The private key must stay secret. Visit Notifications and choose **Enable desktop alerts** on each browser/device. Team task comments and progress posts create in-app notifications and send push alerts to subscribed devices. Push is best-effort and depends on the browser and operating system's push support.

## Docker: PostgreSQL and Redis

Install Docker Desktop, then run:

```powershell
docker compose up --build
```

Open http://127.0.0.1:8000/. Docker Compose starts PostgreSQL, Redis, and the Django ASGI server. The local compose credentials are for development only. Stop the containers with `Ctrl+C`; use `docker compose down` to stop and remove the containers while keeping the database volume.

## What the added pieces do

- `tasks/`: Django app with team and project models, templates, team access checks, notifications, API, WebSocket consumer, and tests.
- `config/asgi.py`: serves regular HTTP pages and authenticated WebSocket connections.
- `/api/auth/token/`: obtain a DRF token by posting `username` and `password`.
- `/api/teams/<team_id>/tasks/`: list or create tasks for a team the signed-in user belongs to. The matching detail URL supports read, update, and delete under team access rules.
- `/calendar/`: see team task due dates by month.
- `/analytics/export.csv`: download a task report for the active team or a selected project.
- Task files and profile pictures are stored in the local `media/` folder and served through signed-in, team-checked views during development. For public deployment, configure durable private file storage.
- `.github/workflows/django.yml`: runs Django checks, migration consistency checks, and tests on GitHub pushes and pull requests.
- `Dockerfile` and `docker-compose.yml`: local container setup with PostgreSQL and Redis.

## Running checks

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Deployment notes

The project is prepared to use PostgreSQL through `DATABASE_URL`, Redis through `REDIS_URL`, and a hosted service such as Render through environment variables. WebSocket live updates use an in-memory channel layer when Redis is not configured; that is suitable for local development only. For a multi-worker public deployment, configure Redis, a production `SECRET_KEY`, `ALLOWED_HOSTS`, HTTPS/CSRF settings, a PostgreSQL database, and an ASGI server. This repository change does not create a hosting account, publish the code, or deploy the site.

Due-date reminders are currently shown as overdue task indicators. Scheduled email or push reminders need a task scheduler and email/push provider, neither of which is configured here.
