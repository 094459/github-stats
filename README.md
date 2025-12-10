# GitHub Traffic Monitor

Minimal web application to monitor GitHub repository traffic data. You will need a valid GitHub key to use this tool. Your key is used to access the traffic data via the GitHub API.

This project is simple, and designed to be a starter project for you to build from. You can extend this using your favorite AI coding tools like Kiro and Amazon Q Developer. The GitHub API is included in the [docs here](/docs/api.github.com.json), which you should provide as context to help it navigate the API when writing code.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open [http://127.0.0.1:5001](http://127.0.0.1:5001)

## Usage

1. Go to Settings and add your GitHub Personal Access Token
2. Add repositories you want to monitor
3. Click on the COLLECT button to download the data from the repositories you have added
4. View traffic data on the Dashboard

![demo dashboard](/images/github-stats-demo.png)

## Features

- Secure token storage
- Repository management
- Traffic visualization (Views vs Clones)
- Historical data tracking
- Responsive design
- Manual data collection