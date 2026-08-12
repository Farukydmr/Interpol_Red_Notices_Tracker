# Interpol Red Notices Tracker

This project is a microservices-based tracking system designed to monitor Interpol's public Red Notices database. It automatically fetches data, bypasses common bot protections, and displays updates in real-time on a web dashboard.

## Project Overview

Scraping public APIs often presents challenges such as rate limiting and Web Application Firewalls (WAF) like Cloudflare. Standard HTTP requests are frequently blocked or restricted.

This system is built to circumvent these limitations efficiently. It continuously scans the Red Notices database to detect whether a new individual has been added or if an existing record has been updated, all while maintaining a legitimate browser footprint.

## System Architecture

The application is containerized using Docker and is split into three core microservices:

### 1. The Scraper (`container_a`)
This service is responsible for data extraction. Rather than using standard libraries or resource-heavy browser automation tools, it utilizes the `curl_cffi` Python package. This library spoofs TLS and JA3 fingerprints to mimic a legitimate Google Chrome browser, successfully bypassing bot detection mechanisms.
To track changes, the scraper maintains a lightweight SQLite database. It generates and stores MD5 hashes of the retrieved records, allowing the system to instantly recognize new entries or modifications to existing ones.

### 2. Message Broker (`container_c`)
To ensure reliable communication between the scraper and the frontend, the system uses RabbitMQ. When the scraper detects a change, it pushes a payload to a RabbitMQ queue. This decoupling guarantees that no data is lost during processing or if the web interface is temporarily offline.

### 3. Web Dashboard (`container_b`)
A Flask-based web application serves as the frontend interface. It consumes the messages delivered by RabbitMQ and visualizes the tracking data and system status on a clean dashboard.

## Software Testing

The project includes both manual simulation tools and automated unit tests to ensure system integrity. All testing-related files are located in the `code_tester_object` directory.

### 1. Automated Unit Tests
The automated tests are written using Python's built-in `unittest` framework and use temporary SQLite databases to prevent interfering with actual application data.

- **`test_scraper.py`**: Verifies the core logic of `container_a`. It specifically tests the MD5 hashing algorithm to ensure that dictionary key ordering does not affect the generated hash, which is critical for detecting genuine record updates.
- **`test_storage.py`**: Verifies the database operations of `container_b`. It tests whether a mocked payload is successfully written into the SQLite database and correctly formatted (e.g., converting nationality lists to comma-separated strings) when retrieved.

**How to run the unit tests:**
From the root directory, execute the following command:
```bash
python -m unittest discover -s code_tester_object
```

### 2. Manual Message Simulation
- **`doc-test.py`**: A manual testing script that acts as a mock producer. It connects directly to the RabbitMQ instance on `localhost` and publishes simulated payloads (e.g., `NEW_CRIMINAL` or `UPDATED`). This is highly useful for verifying the frontend dashboard's real-time UI updates without waiting for the actual scraper to detect live changes.

## How to Run Locally

The entire system can be deployed easily using Docker. Ensure you have Docker and Docker Compose installed on your machine before proceeding.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Farukydmr/Interpol_Red_Notices_Tracker.git
   cd Interpol_Red_Notices_Tracker
   ```

2. **Build and start the services:**
   ```bash
   docker-compose up --build
   ```

3. **Access the dashboard:**
   Once the services are running, open a web browser and navigate to:
   ```text
   http://localhost:5000
   ```

4. **Stop the services:**
   When you are done, you can stop and remove the containers by running:
   ```bash
   docker-compose down
   ```

## Disclaimer

This project is developed for educational and research purposes only, specifically to demonstrate API interaction, fingerprint spoofing, and microservice integration. All scraped data belongs to INTERPOL. The author holds no responsibility for the misuse of this software.
