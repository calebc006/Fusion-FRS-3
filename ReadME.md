# Real-time Facial Recognition System 3

## Description

This repository contains all the source code for Fusion FRS 3 (initially released Feb 2026). 

FRS 3 is a web application for real-time facial recognition. Used for attendance taking for events and army/unit showcases.

`/simplifry` contains the core FRS software used for deployment. **SimpliFRy** is a locally-hosted web application built using Python 3.10 and [Flask](https://github.com/pallets/flask). It makes use of the [`buffalo_l`](https://github.com/deepinsight/insightface/blob/master/python-package/README.md#model-zoo) model by [InsightFace](https://github.com/deepinsight/insightface) for face detection and generation of embeddings as well as Spotify's [Voyager](https://github.com/spotify/voyager) for approximate-nearest-neighbor search.

`/gotendance` is the companion to **SimpliFRy**. It is a lightweight attendance-tracking application built in Go that processes real-time results from SimpliFRy for automated attendance taking.

`/interactiveFR` is a showcase version of FRS. Much of the backend is similar to **SimpliFRy**, but it allows users to capture their faces and add themselves to the database while the app is running.

---

## Table of Contents

- [Features](#features)
- [Installation & Setup](#installation--setup)
- [Usage](#usage)
- [Architecture](#architecture)
- [Data Preparation](#data-preparation)
- [Acknowledgements](#acknowledgements)

---

## Features

As compared to previous iterations, **FRS 3** has the following key improvements:

- Massively improved back-end performance and reliability via code optimizations. Eliminated previous issues of lag, crashing and instability.
- Added optional input configuration for users: description, table number (for new seating feature), sorting index (for priority of display), filter tag(s).
- Introduced InteractiveFR, using a similar backend as SimpliFRy.
- Lightweight, containerized deployment with Docker Compose.
- Easy integration between SimpliFRy (recognition) and Gotendance (attendance tracking).

For a detailed list of changes, refer to [changelog.md](./changelog.md)

---

## Installation & Setup (SimpliFRy + Gotendance)

For installation and setup of InteractiveFR, refer to the application specific [ReadME](interactiveFR\ReadME.md).

### Prerequisites

- [Docker](https://www.docker.com/products/docker-desktop/) and [Docker Compose](https://docs.docker.com/compose/install/)
- [Nvidia Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (for GPU support in Docker)
- [Python 3.10](https://www.python.org/downloads/) (for local development without Docker)
- [Go 1.23.0+](https://go.dev/doc/install) (for building Gotendance locally)

### Quick Start with Docker Compose (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/calebc006/Fusion-FRS-3.git
   cd Fusion-FRS-3
   ```

2. Build the Docker images:
   ```bash
   docker compose build
   ```

3. Start both services:
   ```bash
   docker compose up
   ```

4. Access the applications:
   - **SimpliFRy**: http://localhost:1333
   - **Gotendance**: http://localhost:1500

### Building Individual Services

For development or custom setups, refer to:
- [SimpliFRy Installation Guide](./simpliFRy/ReadME.md#installation)
- [Gotendance Installation Guide](./gotendance/ReadME.md#installation)
- [InteractiveFR Installation Guide](./interactiveFR/ReadME.md#install-and-run)

### Local Development Setup

For development without Docker:

**SimpliFRy:**
```bash
cd simpliFRy
python -m venv venv
venv\Scripts\activate  # On macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
# Access at http://localhost:1333
```

**Gotendance:**
```bash
cd gotendance
go build
./gotendance.exe  # On Linux/macOS: ./gotendance
# Access at http://localhost:1500
```

---

## Usage

### Docker Compose Setup (Both Services)

Once both containers are running:

#### SimpliFRy (Port 1333)
1. Open http://localhost:1333 in your browser
2. Load a personnel dataset (see [Data Preparation](#data-preparation))
3. Start a video stream from your camera
4. Begin facial recognition

#### Gotendance (Port 1500)
1. Open http://localhost:1500 in your browser
2. Load the same personnel dataset
3. Connect to SimpliFRy's result stream:
   - **URL**: `http://<my.ip.address>:1333/api/frResults`
   - This uses the Docker service name for container-to-container communication
4. Gotendance will automatically track attendance as SimpliFRy recognizes faces

#### Connecting Services

Multiple instances of SimpliFRy (running of different computers) can be connected to the same instance of Gotendance, for centralized attendance tracking. 

| Scenario | URL to use in Gotendance |
|----------|-------------------------|
| Both in Docker on the same machine | `http://simplifry:1333/api/frResults` OR `http://<host.ip.address>:1333/api/frResults` |
| SimpliFRy on external machine | `http://<external.ip.address>:1333/api/frResults` |

#### Configuration

Edit environment variables in `.env` to customize:

```py
APP_IP=0.0.0.0
APP_PORT=1334
APP_ENV=production # "production" or "development"

# Out of 100. Higher is better, but costs more latency and bandwidth
STREAM_JPG_QUALITY=90
WIDTH=1920
HEIGHT=1080 

# Input resolution for inference; 4:3 aspect ratio recommended for HIKVISION cameras
INFERENCE_WIDTH=640
INFERENCE_HEIGHT=480
```

---

## Data Preparation

To set up facial recognition, you need to prepare a JSON file mapping images to people.

### Directory Structure

```
simpliFRy/
├── data/
│   ├── logs/              # Auto-generated logs
│   ├── flags/             # Optional: flag images
│   ├── pictures/          # Your reference images
│   │   ├── john_doe1.jpg
│   │   ├── john_doe2.png
│   │   └── caleb.png
│   └── namelist.json      # Personnel mapping file
└── other files
```

### JSON Format

**Minimal format (required):**
```json
{
    "img_folder_path": "pictures",
    "details": [
        {
            "name": "John Doe",
            "images": ["john_doe1.jpg", "john_doe2.png"]
        },
        {
            "name": "3SG CALEB CHIA",
            "images": ["caleb.png"]
        }
    ]
}
```

**Extended format (optional features):**
```json
{
    "img_folder_path": "pictures",
    "flag_folder_path": "flags",
    "details": [
        {
            "name": "John Doe",
            "images": ["john_doe1.jpg", "john_doe2.png"],
            "description": "Company Commander",
            "table_number": 1,
            "sort_index": 0,
            "tags": ["Officer", "HQ"]
        }
    ]
}
```

### Loading Data

1. **Via SimpliFRy UI**: Upload JSON file in settings page
2. **Via Gotendance UI**: Upload the same JSON file in home page
3. Both services use the same format, so you only need one JSON file

---


## Recommended HIKVISION Camera Settings

In Fusion Company, we typically use HIKVISION IP cameras to provide RTSP input during deployment. As of Feb 2026, we use the HIKVISION iDS-2CD7A46G0-IZHS. 

Video settings can be adjusted in the HIKVISION Video Management Software, which can be accessed by typing the IP address of the camera into the search bar of your browser. These are the typical settings we use, to balance low-latency and acceptable video quality.

![Video Settings](./simpliFRy/assets/image.png)

Image settings can also be changed to adjust exposure, contrast, dynamic range and more. These should be tuned to ensure a clear image given the lighting conditions of the deployment site. 


---

## Architecture

### SimpliFRy
- **Backend**: Python 3.10 + Flask
- **Face Detection**: InsightFace (buffalo_l model)
- **Embedding Search**: Spotify Voyager (ANN)
- **Output**: HTTP streaming JSON responses at `/api/frResults`

### Gotendance
- **Backend**: Go 1.23.0
- **Frontend**: Vanilla HTML/CSS/JavaScript
- **Input**: HTTP streaming from SimpliFRy
- **Output**: Attendance records in JSON format
- **No external runtime dependencies** (standalone binary)

### InteractiveFR
- Similar backend to SimpliFRy
- Allows real-time face capture and database updates
- Used for demonstrations and interactive setups

---


## License 

This project is [licensed](./LICENSE) under Apache 2.0.

&copy; Fusion Company, 11C4I Battalion, Singapore Armed Forces 

---

## Acknowledgements

We acknowledge the past versions of FRS, built by our seniors in Fusion Coy; much in this project is owed to their efforts.
- v2.2: https://github.com/Cooleststar/FUSION-FR
- v2.1: https://github.com/plainpotato/FR-FUSION
- v2.0: https://github.com/CJBuzz/Real-time-FRS-2.0
- v1.0: https://github.com/CJBuzz/FRS

Special thanks to:
- [**Cooleststar**](https://github.com/cooleststar): The long-time maintainer of FRS v2.0-v2.2. Without his efforts this project could not have survived for my generation to see.
- [**Ruihongc**](https://github.com/ruihongc): Suggesting the use of Spotify's Voyager which led to much faster embedding search compared to previous methods.
- [**BabyWaffles**](https://github.com/BabyWaffles): Dockerization of simpliFRy was made possible by his extensive help.
- [**CJBuzz**](https://github.com/CJBuzz): One of the first few developers of this project.
- [**plainpotato**](https://github.com/plainpotato): Provided support for a big part of the project.
- [**bryannyp**](https://github.com/bryannyp): Built the UI for the Gotendance app
