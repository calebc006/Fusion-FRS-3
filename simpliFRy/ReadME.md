# SimpliFRy

![Project Logo](static/images/favicon.png)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation](#installation)
- [Pages & Endpoints](#pages--endpoints)
- [Configuration](#configuration)
- [Data Directory](#data-directory)
- [Advanced Configuration](#advanced-configuration)

---

## Overview

**SimpliFRy** is the core facial recognition component of **FRS 3**. It is a locally-hosted web application built using Python 3.10 and [Flask](https://github.com/pallets/flask), providing real-time face detection, embedding generation, and result streaming.

For integration with Gotendance or deployment instructions, refer to the [main README](../ReadME.md).  
For the technical deep dive, see the [Developer Guide](./Developer%20Guide.md)

---

## Architecture

### Technology Stack
- **Backend**: Python 3.10 + Flask web framework
- **Face Detection**: [InsightFace](https://github.com/deepinsight/insightface) library (buffalo_l model)
- **Embedding Search**: [Spotify Voyager](https://github.com/spotify/voyager) for approximate-nearest-neighbor search
- **Video Processing**: FFmpeg integration
- **Deployment**: Docker containers with optional GPU support (NVIDIA CUDA)

### Key Components
- **Video Stream Handler**: Manages RTSP/HTTP video input
- **Face Detection Engine**: Detects faces and generates embeddings
- **Result Broadcaster**: Streams recognition results via HTTP streaming
- **Attendance Manager**: Optionally integrates with Gotendance via `/api/frResults` endpoint

---

## Installation

> For complete setup instructions including Docker, refer to the [main README](../ReadME.md#installation--setup)

### Quick Start

**Using Docker (Recommended):**
```bash
cd simpliFRy
docker compose build
docker compose up
```

**For Local Development:**
```bash
python -m venv venv
venv\Scripts\activate  # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Access the application at **http://localhost:1333**

### Prerequisites
- Python 3.10+ (for local development)
- Docker & Docker Compose (for containerized setup)
- NVIDIA Container Toolkit (optional, for GPU support)
- FFmpeg 8.0.1+ (required)

The `buffalo_l` model will auto-install on first run. A copy of `buffalo_l.zip` is available in the root directory.

## Pages & Endpoints

### Web Pages

- `/` - Main interface for starting video streams and initiating FR
- `/seats` - Seating layout view (for organized venue tracking)
- `/old_layout` - Alternative layout for different use cases
- `/settings` - Configuration and data loading page

### API Endpoints

- `GET /api/frResults` - HTTP streaming endpoint for real-time recognition results  
  - Used by Gotendance to track attendance
  - Returns JSON stream of detected faces with labels

---

## Configuration

### Environment Variables (`.env` file)

Create or modify `.env` in the SimpliFRy directory:

```
APP_IP=0.0.0.0
APP_PORT=1333
APP_ENV=production        # "production" or "development"

# Video settings
STREAM_JPG_QUALITY=75     # JPEG compression (1-100)
WIDTH=1920                # Video resolution width
HEIGHT=1080               # Video resolution height

# Inference settings (optimized for speed/accuracy)
INFERENCE_WIDTH=640       # Model input width
INFERENCE_HEIGHT=480      # Model input height
```

### Runtime Settings (via UI)

Adjustable in the `/settings` page:
- Recognition threshold
- Face detection confidence  
- Embedding search sensitivity
- Display and logging preferences

---

## Data Directory

The `/data` directory is auto-created and contains:

```
data/
├── logs/              # Auto-generated application logs per session
├── captures/          # Optional: captured frames during recognition
├── flags/             # Flag images for display (optional)
├── pictures/          # Reference images for people
└── namelist.json      # Personnel mapping file
```

**Important**: This directory is volume-mounted in Docker, making it the primary way to exchange data with the container.

---

## Advanced Configuration

### Customization

**Page Titles**: Edit HTML templates in `./templates/` to change page titles:
```html
<div class="title">YOUR CUSTOM TITLE</div>
```

**Seating View Background**: Replace `./static/images/seats_bg.png` with your custom venue image.

### Settings Page

Access detailed FR algorithm settings at `/settings`:

| Parameter | Type | Description |
|-----------|------|-------------|
|`name`| String | Display name (must be unique!) |
|`images`| List | Image files for this person |
|`description`| String | Optional description |
|`country_flag`| String | Flag image name |
|`table`| String | Table number (for `/seats` view) |
|`tags`| List | Filter tags for Gotendance |
|`priority`| Integer | Sort order (lower = first) |

For detailed parameter documentation, see the [Developer Guide](./Developer%20Guide.md#configuration).