FROM python:3.10.12-slim

RUN apt-get update && apt-get install -qq -y \
    build-essential libpq-dev --no-install-recommends \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Because the build context is the project root ("."),
# we must specify the subfolder for requirements.txt:
COPY katana-pqc-return/requirements.txt . 
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Now copy the 'katana' folder from inside katana-pqc-return
COPY katana-pqc-return/katana ./katana
EXPOSE 4443

CMD ["gunicorn", "-b", "0.0.0.0:4443", "katana.app:create_app()"]
