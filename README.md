# Trader Scripts - Arbitrage Monitor

This repository contains scripts to monitor arbitrage opportunities between cryptocurrency exchanges (Kraken and Coinbase).

## Features
- Monitors live cryptocurrency prices.
- Calculates arbitrage opportunities.
- Logs data to both the console and a log file.
- Supports real-time updates with a dynamic console interface.
- Self-contained Docker environment for deployment.

---

## Prerequisites
1. **Docker**: Ensure Docker is installed on your system.
   - Install Docker: [https://docs.docker.com/get-docker/](https://docs.docker.com/get-docker/)
2. **Docker Compose**: Ensure Docker Compose is installed.
   - Install Docker Compose: [https://docs.docker.com/compose/install/](https://docs.docker.com/compose/install/)

---

## Setup

### 1. Clone the Repository
```bash
git clone https://github.com/josephgithin/trader-scripts.git
cd trader-scripts/arbitrage
```

### 2. Environment Variables
The application uses environment variables set inside the Dockerfile and `docker-compose.yml`. Update them as needed.

### 3. Build the Docker Image
```bash
docker-compose build
```

### 4. Run the Application
```bash
docker-compose up
```
> **Note:** This runs in interactive mode to display real-time updates.

- **Detach**: Press `CTRL + P, CTRL + Q`
- **Reattach**: Run
  ```bash
  docker attach exchange-monitor
  ```

### 5. Stop the Application
```bash
docker-compose down
```

---

## Logs

### View Logs in Real-Time
```bash
docker-compose logs -f
```

### View Logs Inside the Container
```bash
docker exec -it exchange-monitor sh
cat /app/logs/exchange_monitor.log
```

---

## Customization

### Update Monitoring Parameters
- Edit `config.json` for custom parameters.
- Update exchange APIs or endpoints in `config.py`.

### Dynamic Console Table (Optional)
- Install **rich** for dynamic tables (already handled in the Dockerfile).
  ```bash
  pip install rich
  ```

---

## Troubleshooting

### 1. Logs Not Displaying
- Ensure the environment variable `PYTHONUNBUFFERED=1` is set.
- Check file permissions:
  ```bash
  chmod -R 777 logs
  ```

### 2. Container Crashes or Stops
- Check logs:
  ```bash
  docker logs exchange-monitor
  ```
- Restart:
  ```bash
  docker-compose up --build
  ```

---

## License
This project is licensed under the MIT License. See the LICENSE file for details.

---

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

---

## Author
**Joseph Githin**

[GitHub Repository](https://github.com/josephgithin/trader-scripts.git)


