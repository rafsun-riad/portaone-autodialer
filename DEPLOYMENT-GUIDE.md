# Django + Next.js Deployment Guide (Ubuntu VPS)

> **Stack**
>
> - Ubuntu 24.04
> - Django (Backend)
> - Next.js (Frontend)
> - SQLite
> - Redis
> - Celery Worker
> - Celery Beat
> - Gunicorn
> - Nginx
> - Node.js 24.18.0
> - pnpm
> - uv (dependency manager only)

This guide is intended for a simple VPS deployment.

- No domain
- No HTTPS
- Access by IP only
- SQLite database
- HTTP only

---

# Architecture

```
Internet
      │
      ▼
   Nginx (80)
      │
 ┌────┴─────────────┐
 │                  │
 ▼                  ▼
Next.js          Gunicorn
:3000            :8000
                     │
                  Django
                     │
                  SQLite
                     │
                   Redis
                     │
        Celery Worker + Beat
```

---

# Step 1. Update the server

```bash
sudo apt update
sudo apt upgrade -y
```

Install required packages.

```bash
sudo apt install -y \
git \
curl \
build-essential \
python3 \
redis-server \
nginx
```

Enable services.

```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server

sudo systemctl enable nginx
sudo systemctl start nginx
```

---

# Step 2. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reload shell.

```bash
source ~/.bashrc
```

Verify.

```bash
uv --version
```

---

# Step 3. Install Node.js 24.18.0

```bash
curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -

sudo apt install -y nodejs
```

Verify.

```bash
node -v
npm -v
```

Expected output:

```
v24.18.0
```

---

# Step 4. Install pnpm

```bash
npm install -g pnpm
```

Verify.

```bash
pnpm -v
```

---

# Step 5. Clone the repository

Example:

```bash
cd /opt

git clone https://github.com/USERNAME/PROJECT.git

cd PROJECT
```

> **Note**
>
> We are **not changing ownership** of the project.

---

# Step 6. Backend setup

Go to backend.

```bash
cd backend
```

Install dependencies.

```bash
uv sync
```

Activate environment.

```bash
source .venv/bin/activate
```

---

# Step 7. Install Gunicorn

```bash
uv pip install gunicorn
```

or if Gunicorn is already in your project dependencies,

```bash
uv sync
```

---

# Step 8. Configure environment

Create `.env`.

Example:

```text
DEBUG=False

SECRET_KEY=your-secret-key

ALLOWED_HOSTS=YOUR_SERVER_IP

REDIS_URL=redis://127.0.0.1:6379/0
```

---

# Step 9. Run migrations

```bash
python manage.py migrate
```

Create admin user.

```bash
python manage.py createsuperuser
```

Collect static files.

```bash
python manage.py collectstatic --noinput
```

---

# Step 10. Test Gunicorn

```bash
gunicorn config.wsgi:application \
--bind 0.0.0.0:8000 \
--workers 3
```

Visit

```
http://YOUR_SERVER_IP:8000
```

Stop with

```
Ctrl+C
```

---

# Step 11. Frontend setup

Go to frontend.

```bash
cd ../frontend
```

Install packages.

```bash
pnpm install
```

Create

```
.env.production
```

Example

```text
NEXT_PUBLIC_API=http://YOUR_SERVER_IP/api
```

Build.

```bash
pnpm build
```

Test.

```bash
pnpm start
```

Visit

```
http://YOUR_SERVER_IP:3000
```

---

# Step 12. Test Celery

Worker

```bash
cd ../backend

source .venv/bin/activate

celery -A config worker -l info
```

Beat

```bash
celery -A config beat -l info
```

---

# Step 13. Create Gunicorn service

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

```ini
[Unit]
Description=Gunicorn Django Service
After=network.target

[Service]
User=<YOUR_USERNAME>
Group=<YOUR_USERNAME>

WorkingDirectory=/opt/PROJECT/backend

Environment="PATH=/opt/PROJECT/backend/.venv/bin"

ExecStart=/opt/PROJECT/backend/.venv/bin/gunicorn \
config.wsgi:application \
--workers 3 \
--bind 127.0.0.1:8000

Restart=always

[Install]
WantedBy=multi-user.target
```

---

# Step 14. Create Next.js service

```bash
sudo nano /etc/systemd/system/nextjs.service
```

```ini
[Unit]
Description=Next.js Service
After=network.target

[Service]
User=<YOUR_USERNAME>

WorkingDirectory=/opt/PROJECT/frontend

Environment=PORT=3000

ExecStart=/usr/bin/pnpm start

Restart=always

[Install]
WantedBy=multi-user.target
```

---

# Step 15. Create Celery Worker service

```bash
sudo nano /etc/systemd/system/celery.service
```

```ini
[Unit]
Description=Celery Worker
After=network.target

[Service]
User=<YOUR_USERNAME>

WorkingDirectory=/opt/PROJECT/backend

Environment="PATH=/opt/PROJECT/backend/.venv/bin"

ExecStart=/opt/PROJECT/backend/.venv/bin/celery \
-A config worker \
-l info

Restart=always

[Install]
WantedBy=multi-user.target
```

---

# Step 16. Create Celery Beat service

```bash
sudo nano /etc/systemd/system/celerybeat.service
```

```ini
[Unit]
Description=Celery Beat
After=network.target

[Service]
User=<YOUR_USERNAME>

WorkingDirectory=/opt/PROJECT/backend

Environment="PATH=/opt/PROJECT/backend/.venv/bin"

ExecStart=/opt/PROJECT/backend/.venv/bin/celery \
-A config beat \
-l info

Restart=always

[Install]
WantedBy=multi-user.target
```

---

# Step 17. Enable services

```bash
sudo systemctl daemon-reload

sudo systemctl enable gunicorn
sudo systemctl enable nextjs
sudo systemctl enable celery
sudo systemctl enable celerybeat

sudo systemctl start gunicorn
sudo systemctl start nextjs
sudo systemctl start celery
sudo systemctl start celerybeat
```

Check status.

```bash
sudo systemctl status gunicorn
sudo systemctl status nextjs
sudo systemctl status celery
sudo systemctl status celerybeat
```

View logs.

```bash
journalctl -u gunicorn -f

journalctl -u nextjs -f

journalctl -u celery -f

journalctl -u celerybeat -f
```

---

# Step 18. Configure Nginx

Remove default site.

```bash
sudo rm /etc/nginx/sites-enabled/default
```

Create configuration.

```bash
sudo nano /etc/nginx/sites-available/project
```

```nginx
server {

    listen 80;

    server_name _;

    client_max_body_size 100M;

    location / {

        proxy_pass http://127.0.0.1:3000;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /admin/ {

        proxy_pass http://127.0.0.1:8000;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {

        proxy_pass http://127.0.0.1:8000;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {

        alias /opt/PROJECT/backend/staticfiles/;
    }

    location /media/ {

        alias /opt/PROJECT/backend/media/;
    }

}
```

Enable configuration.

```bash
sudo ln -s /etc/nginx/sites-available/project \
/etc/nginx/sites-enabled/
```

Test.

```bash
sudo nginx -t
```

Reload.

```bash
sudo systemctl reload nginx
```

---

# Step 19. Configure firewall (optional)

If UFW is enabled.

```bash
sudo ufw allow OpenSSH

sudo ufw allow 80/tcp

sudo ufw enable
```

---

# Step 20. Test deployment

Application

```
http://YOUR_SERVER_IP
```

Admin

```
http://YOUR_SERVER_IP/api/admin/
```

---

# Updating after code changes

Pull latest changes.

```bash
cd /opt/PROJECT

git pull
```

Backend.

```bash
cd backend

uv sync

source .venv/bin/activate

python manage.py migrate

python manage.py collectstatic --noinput

sudo systemctl restart gunicorn

sudo systemctl restart celery

sudo systemctl restart celerybeat
```

Frontend.

```bash
cd ../frontend

pnpm install

pnpm build

sudo systemctl restart nextjs
```

---

# Useful commands

Restart all services.

```bash
sudo systemctl restart gunicorn
sudo systemctl restart nextjs
sudo systemctl restart celery
sudo systemctl restart celerybeat
sudo systemctl restart nginx
```

Service status.

```bash
sudo systemctl status gunicorn
sudo systemctl status nextjs
sudo systemctl status celery
sudo systemctl status celerybeat
sudo systemctl status nginx
```

Logs.

```bash
journalctl -u gunicorn -f
journalctl -u nextjs -f
journalctl -u celery -f
journalctl -u celerybeat -f
journalctl -u nginx -f
```
