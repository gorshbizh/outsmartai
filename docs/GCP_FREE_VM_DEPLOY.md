# Deploy OutSmartAI on a Free-Tier GCP VM

This guide deploys the whole stack on one Google Compute Engine VM:

- `frontend`: Node/Express container serving the whiteboard app
- `backend`: Flask/Gunicorn container
- `mysql`: MySQL 8 container

All three services run with `docker compose` on one machine. The frontend is exposed on port `80`. The backend and MySQL stay on the private Docker network.

## 1. Create the Google Cloud project

1. In Google Cloud Console, create a new project.
2. Attach a billing account.
3. Enable the Compute Engine API.
4. Pick one always-free region: `us-west1`, `us-central1`, or `us-east1`.

## 2. Create the VM

Create one VM with these settings:

- Machine type: `e2-micro`
- Region: `us-west1` is a good default
- Boot disk: Debian 12 or Ubuntu 22.04 LTS
- Boot disk size: keep the total standard persistent disk usage within the free-tier allowance
- Firewall: allow HTTP traffic

Example with `gcloud`:

```bash
gcloud compute instances create outsmartai-dev \
  --project YOUR_PROJECT_ID \
  --zone us-west1-b \
  --machine-type e2-micro \
  --image-family debian-12 \
  --image-project debian-cloud \
  --boot-disk-size 20GB \
  --boot-disk-type pd-standard \
  --tags http-server
```

If you prefer the console, use the same settings there.

## 3. SSH into the VM

```bash
gcloud compute ssh outsmartai-dev --zone us-west1-b
```

## 4. Install Docker and the Compose plugin

On the VM:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

## 5. Copy the repo to the VM

Use whichever path is easiest for you.

Option A:

```bash
git clone YOUR_REPO_URL outsmartai
cd outsmartai
```

Option B:

```bash
gcloud compute scp --recurse /path/to/local/outsmartai outsmartai-dev:~ --zone us-west1-b
cd ~/outsmartai
```

## 6. Create the VM environment file

Start from the example:

```bash
cp .env.gcp.example .env
```

Edit `.env` and set:

- `LLM_PROVIDER`
- `LLM_API_KEY`
- `FLASK_SECRET_KEY`
- `MYSQL_PASSWORD`
- `MYSQL_ROOT_PASSWORD`
- `ADMIN_PASSWORD`

Keep these values as-is for the one-machine Docker deployment:

```env
MYSQL_HOST=mysql
MYSQL_PORT=3306
BACKEND_URL=http://backend:5055
DB_AUTO_INIT=True
DB_AUTO_SEED=False
```

## 7. Start the stack

From the repo root on the VM:

```bash
./deploy-gcp-vm.sh
```

The first startup can take a few minutes because Docker has to build the frontend and backend images.

If you want the script to skip `git pull` because you copied files manually or have local edits on the VM:

```bash
./deploy-gcp-vm.sh --no-pull
```

If you also want recent logs after deployment:

```bash
./deploy-gcp-vm.sh --logs
```

## 8. Verify the deployment

Check service health:

```bash
docker compose -f docker-compose.prod.yml logs backend --tail=100
docker compose -f docker-compose.prod.yml logs frontend --tail=100
docker compose -f docker-compose.prod.yml logs mysql --tail=100
```

The app should be reachable at:

```text
http://VM_EXTERNAL_IP/
```

You can find the IP with:

```bash
gcloud compute instances describe outsmartai-dev \
  --zone us-west1-b \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

## 9. Update the app later

After new commits are on the VM:

```bash
./deploy-gcp-vm.sh
```

## 10. Useful operations

Stop the stack:

```bash
docker compose -f docker-compose.prod.yml down
```

Stop and remove containers but keep MySQL data:

```bash
docker compose -f docker-compose.prod.yml down
```

Rebuild only app containers:

```bash
docker compose -f docker-compose.prod.yml build frontend backend
docker compose -f docker-compose.prod.yml up -d
```

Reset everything including the MySQL data volume:

```bash
docker compose -f docker-compose.prod.yml down -v
```

## Notes

- The frontend publishes host port `80`, so you only need the VM's HTTP firewall rule.
- MySQL is not exposed on the VM, which is what we want for this single-machine setup.
- Backend uploads and image backups are stored in named Docker volumes.
- `deploy-gcp-vm.sh` is the normal redeploy command to use on the VM.
- This is a good dev-stage deployment. For a real production environment, move MySQL to a managed service and add HTTPS plus secret management.
