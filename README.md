# MISP reporting

Create reports of MISP usage.

# Setup

Get the repository 

```
mkdir /var/www/MISP/misp-custom/reporting
git clone https://github.com/cudeso/misp-reporting.git
cd misp-reporting
```

Setup the virtual environment

```
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

Confgure, adjust MISP credentials, location, etc.

```
cp config.py.default config.py
```

Create the output locations

```
mkdir /var/www/MISP/app/webroot/misp-reporting/
mkdir /var/www/MISP/app/webroot/misp-reporting/assets
```

Copy logo and organisation logos in assets directory

Then run the reporting script

```
python reporting.py
```

# Cronjob


# Demo

![docs/demo1.jpg](docs/demo1.jpg)

![docs/demo2.jpg](docs/demo2.jpg)

![docs/demo3.jpg](docs/demo3.jpg)

![docs/demo4.jpg](docs/demo4.jpg)

![docs/demo5.jpg](docs/demo5.jpg)

![docs/demo6.jpg](docs/demo6.jpg)