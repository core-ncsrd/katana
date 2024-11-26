# Service Creation Time

Script that creates slice based on the provided NEST, gets the Service Creation Time measurements and
exports that to an InfluxDB and to a CSV file

## Installation

```bash
pip3 install .
```

## Usage

```bash
sct --url URL --nest NEST --iterations I --database DB_URL --csv CSV
```

### Example

```bash
sct --url 10.30.0.180:8000 \
--iterations 25 \
--csv output.csv \
--nest ~/nest_4g_embb.json \
--database user:password@10.30.0.238:8086/service_creation_time
```

### Options

#### --url | -u (Required)

The url of Katana Slice Manaer that will be used. It must be in the form: `host_ip:port`

#### --nest | -n (Required)

The NEST JSON file that will be used for the created slice

#### --iterations | -i (Optional)

The number of the iterations. By default it is 25

#### --database | -d (Optional)

The URL of the Influx DB where the results will be exported. It must be in the form: `username:password@host:port/db`

> If no db url is provided, the results will be exported by default on a CSV file

#### --csv | -c (Optional)

The CSV file where the results will be exported

> If neither csv file nor database URL is provided, the results will be exported by default at ./output.csv
