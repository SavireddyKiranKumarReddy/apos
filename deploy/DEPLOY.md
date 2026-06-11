# Hosting pdfsmith

The Docker image is self-contained (app + Ghostscript + LibreOffice +
Tesseract) and stateless — files are processed in memory and never stored —
so it runs anywhere a container runs. Pick whichever host you like:

## Any VPS (the cheapest real option)

A 1 vCPU / 1 GB box (Hetzner, DigitalOcean, Lightsail…) is plenty to start.

```bash
git clone https://github.com/vishalblz10/pdfsmith && cd pdfsmith
docker compose up -d --build
```

Put Caddy in front for automatic HTTPS — `/etc/caddy/Caddyfile`:

```
pdf.yourdomain.com {
    reverse_proxy 127.0.0.1:8000
    request_body {
        max_size 120MB
    }
}
```

## Fly.io

```bash
fly launch --no-deploy        # answer the prompts; it detects the Dockerfile
fly deploy
```

Suggested `fly.toml` additions:

```toml
[http_service]
  internal_port = 8000
  force_https = true

[[vm]]
  memory = "1gb"              # LibreOffice conversions want headroom
```

## Render

Create a **Web Service → Build from a Git repo**, pick this repository,
choose **Docker** as the runtime, and set the port to `8000`. The free tier
works for demos (it sleeps when idle); the starter tier keeps it warm.

## Railway

`railway init` → deploy from repo → it picks up the Dockerfile automatically.
Set `PDFSMITH_MAX_MB` in the service variables if you want a different cap.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `PDFSMITH_MAX_MB` | `50` | per-request upload cap |

## Notes for production

- The container runs read-only with a tmpfs `/tmp` (see docker-compose.yml);
  conversions that need scratch space use it and clean up after themselves.
- Memory is the resource to watch: LibreOffice and OCR are the hungry tools.
  1 GB RAM is comfortable; 512 MB works if you skip Office/OCR.
- If you put it behind a proxy, raise the proxy's body-size limit to match
  `PDFSMITH_MAX_MB` (Caddy example above; for nginx set
  `client_max_body_size`).
- Want a lighter image without LibreOffice/OCR? Delete those apt packages
  from the Dockerfile — the UI will grey those tools out automatically and
  everything else keeps working.
