<!-- omit from toc -->
# SimpliFRy

![Project Logo](static/images/favicon.png)

---

<!-- omit from toc -->
## Table of Contents

- [Description](#description)
- [Installation](#installation)
- [Usage](#usage)
- [Pages](#pages)
- [`/data`](#data)
- [`.env`](#env)
- [Settings](#settings)
- [Data Preparation](#data-preparation)

---

## Description

**SimpliFRy** is the core component for deployment of **FRS 3**. It is a locally-hosted web application built using Python 3.10 and [Flask](https://github.com/pallets/flask), and makes use of the [InsightFace](https://github.com/deepinsight/insightface) library by deepinsight for face detection and generation of embeddings as well as the [Voyager](https://github.com/spotify/voyager) library by Spotify for ANN search.

If you are a developer and would like to understand more about how SimpliFRy works, refer to the [Developer Guide](../Developer%20Guide.md)

---

## Installation

### Prerequisites

- [Python 3.10](https://www.python.org/downloads/) (or later)
- [FFmpeg 8.0.1](https://www.ffmpeg.org/download.html) (or later)
- [Docker](https://www.docker.com/products/docker-desktop/) (optional)
- [Nvidia Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (for GPU usage within docker container)

The `buffalo_l` model will auto-install if it is not found on your system. Alternatively, you can install it manually by following the instructions [here](https://github.com/deepinsight/insightface/blob/master/python-package/README.md#model-zoo). A copy of `buffalo_l.zip` can be found in the root directory of this repository.


### Download Source Code

1. Clone the repository:

    ```bash
    git clone https://github.com/calebc006/Fusion-FRS-3.0.git
    ```

2. Navigate to simpliFRy directory

    ```bash
    cd simpliFRy
    ```

### Installation via Docker (Recommended)

1. Build Docker Image
   
    ```bash
    docker compose build
    ```

### Installation via Virtual Environment (For development)

1. First, create a Python virtual environment in the `simpliFRy` directory

    ```bash
    py -m venv venv
    ```

2. Activate it

    ```bash
    venv\Scripts\activate # use source venv/bin/activate for linux and macOS
    ```

3. Install the requirements with pip

    ```bash
    pip install -r requirements.txt # this may take some time!
    ```

---

## Usage

### Docker (Recommended)

To start up a new container from the command line, run the following command from the `simpliFRy` directory

```bash
docker compose up
```

If you already have an existing container, you can simply start by pressing the play button in the Docker Desktop application.

### Virtual Environment (For development)

Activate the Python virtual environment and run the `app.py` script

```bash
venv\Scripts\activate # use source venv/bin/activate for linux and macOS
```

```bash
py app.py
```

Access the application at <http://localhost:1333> (preferably using a Chromium browser)


## Pages

The pages in this application are:

- `localhost:1333`
- `localhost:1333/seats`
- `localhost:1333/old_layout`
- `localhost:1333/settings`

## `.env` 

To configure the Python web server, create a file named `.env` in the `/simpliFRy` directory. Its format should be:

```python
APP_IP=0.0.0.0
APP_PORT=1333
APP_ENV=production # "production" or "development"

STREAM_JPG_QUALITY=75
WIDTH=1920
HEIGHT=1080

# Input resolution for buffalo_l 
INFERENCE_WIDTH=640
INFERENCE_HEIGHT=480
```

## `/data` 

If not present in `/simpliFRy`, create a new folder name `data`.

The `data` directory in `simpliFRy` is a **volume mount** as it is volume mounted to the `/app/data` directory within the docker container. Hence, it is the primary way to pass information to and from the container.

Everytime the app is started, a new `.logs` file will be created in the `/data/logs` directory. It will list key actions undertaken by the simpliFRy app (and any error messages) in that session.

The `data` directory is also where you would store the namelist and database of reference images (more info later).


## Data Preparation

To conduct facial recognition, you need to load images of people you wish to be recognised into simpliFRy. Each person can have 1 or more pictures.

1. From the `simpliFRy/data` folder (created automatically when starting the app), create a new folder with all the images of the people you wish to be detected.

2. In the `simpliFRy/data` folder, create a JSON file (name it whatever you want) that maps the image file name with the name of the person to be recognised.

For example, if `john_doe1.jpg` and `john_doe2.png` are pictures of 'John Doe' while `caleb.png` is a picture of '3SG CALEB', and all images are in a folder called `pictures`, this is the directory structure.

```
simpliFRy/
├── data/
|   ├── logs/
|   ├── flags/
|   |   ├── singapore_flag.png
|   ├── pictures/
|   |   ├── john_doe1.jpg
|   |   ├── john_doe2.png
|   |   └── caleb.png
|   └── namelist.json
└── other files and folders
```

`namelist.json` would look like this:

```json
{
    "img_folder_path": "pictures",
    "details": [
        {
            "name": "John Doe",
            "images": ["john_doe1.jpg", "john_doe2.png"],
        },
        {
            "name": "3SG CALEB CHIA",
            "images": ["caleb.png"],
        }
    ]
}
```

There are optional parameters that can be added to unlock more features. A "fully configured" JSON file would look something like this: 

```json
{
    "img_folder_path": "pictures",
    "flag_folder_path": "flags",
    "details": [
        {
            "name": "John Doe",
            "images": ["john_doe1.jpg", "john_doe2.png"],
            "description": "someone",
            "country_flag": "singapore_flag.png",
            "table": "T1",
            "tags": ["Army", "DIS"],
            "priority": 2
        },
        {
            "name": "3SG CALEB CHIA",
            "images": ["caleb.png"],
            "description": "someone else",
            "country_flag": "singapore_flag.png",
            "table": "VIP",
            "tags": ["Air Force"],
            "priority": 1
        }
    ]
}
```

| Parameter | Type | Description | Required? |
|-----------|--------|--------------------------|-------|
|`img_folder_path`| String | The path to the folder with all the user images relative to `/data`| Y |
|`flag_folder_path`| String | The path to the folder with all the country flags relative to `/data`| |
|`name`| String | The display name of the user (must be unique!) | Y |
|`images`| List[String] | List of image names within `img_folder_path`| Y |
|`description`| List[String] | Optional description to be displayed alongside `name` | |
|`country_flag`| String | Image name for the flag to be displayed on `/welcome` page | |
|`table`| String | The table name that is used for the `/seats` table lighting functionality | |
|`tags`| List[String] | Optional list of filter tags used in Gotendance | |
|`priority`| Integer | Determines the sorting order in detection lists (lower number = shown first). If two people have the same priority or no priority is set, they are sorted alphabetically | |


## Settings

To adjust parameters used in the FR algorithm, go to <http://localhost:1333/settings>

![simpliFRy settings page](assets/settings_page.png)

For more information on the parameters, click [here](../Developer%20Guide.md#configuration)

To adjust camera settings, refer to [this guide](../ReadME.md#recommended-hikvision-camera-settings).


## Display Customization

To customize titles for a page, go to the page's html file (e.g. `./templates/old_layout.html`), locate the title div and make the necessary changes: `<div class="title">MY NEW TITLE</div>` 

For the `/seats` page, the image can be changed by replacing the image in `./static/images/seats_bg.png` with any other image (keep the file name the same!).