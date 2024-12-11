# MISP reporting

Create reports of MISP usage.

# Setup

```
mkdir /var/www/MISP/misp-custom/reporting
git clone https://github.com/cudeso/misp-reporting.git
cd misp-reporting
cp config.py.default config.py
```

Adjust credentials

```
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

```
mkdir /var/www/MISP/app/webroot/misp-reporting/
mkdir /var/www/MISP/app/webroot/misp-reporting/assets
```

Copy logo and organisation logos

```
python reporting.py
```