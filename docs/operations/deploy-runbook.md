# Deploy Runbook

## Standard Deployment Process

```bash
# 1. Verify CI green on master
gh run list -R thinkneo-ai/mcp-server --workflow tests.yml --limit 1

# 2. Tag release
git tag vX.Y.Z -m "vX.Y.Z — description"
git push origin vX.Y.Z

# 3. SSH to production
ssh root@161.35.12.205

# 4. Navigate to repo
cd /opt/thinkneo-mcp-server

# 5. Backup
docker tag thinkneo-mcp-server:latest thinkneo-mcp-server:rollback
sudo -u postgres pg_dump thinkneo_mcp > /tmp/backup_$(date +%Y%m%d_%H%M).sql

# 6. Pull latest
git fetch origin
git status  # must be clean (only docker-compose.yml modified is OK)
git pull origin master

# 7. Build new image
docker build -t thinkneo-mcp-server:vX.Y.Z .
docker tag thinkneo-mcp-server:vX.Y.Z thinkneo-mcp-server:latest

# 8. Deploy
docker compose down
docker compose up -d

# 9. Verify (wait for health)
sleep 10
curl -sf https://mcp.thinkneo.ai/mcp/docs  # expect 200

# 10. Smoke tests
bash scripts/audit_live.sh  # expect 20/20

# 11. Monitor logs 30 min
docker logs -f thinkneo-mcp-server
```

## Emergency Rollback

```bash
ssh root@161.35.12.205
docker stop thinkneo-mcp-server
docker tag thinkneo-mcp-server:rollback thinkneo-mcp-server:latest
docker compose up -d
sleep 10
curl -sf https://mcp.thinkneo.ai/mcp/docs  # verify 200
```

## Common Issues

### git pull shows modified docker-compose.yml
Expected — production docker-compose has environment-specific config. Use `git stash` before pull if needed, then `git stash pop`.

### Container unhealthy after deploy
Check logs: `docker logs thinkneo-mcp-server --tail 50`
Common causes: missing env var, DB connection refused, Python import error.

### NEVER use scp to sync code
SCP creates state divergence. Always use `git pull`. If git is broken, re-clone (see below).

### Git repo corrupted
```bash
cd /opt
mv thinkneo-mcp-server thinkneo-mcp-server.broken
git clone https://github.com/thinkneo-ai/mcp-server.git thinkneo-mcp-server
cp thinkneo-mcp-server.broken/.env thinkneo-mcp-server/
cp thinkneo-mcp-server.broken/docker-compose.yml thinkneo-mcp-server/
docker build -t thinkneo-mcp-server:latest thinkneo-mcp-server/
docker compose -f thinkneo-mcp-server/docker-compose.yml up -d
rm -rf thinkneo-mcp-server.broken
```
