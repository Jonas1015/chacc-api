# OPEN TZ 

This is a python open source API engine created using Fast API. It was first created in August 2025.


## Building with Open TZ Platform
If as a developer you want to start development with Open-Tz Platform, here are things to consider:

Clone project from the repository:
```
git clone github.com/jonas1015/open-tz
```

create virtual environment:
```
python3 -m venv .venv
```

activate virtual environment
> Windows
> ```
> .\.venv\Scripts\activate
> ```

> Ubuntu
> ```
> source .venv/bin/activate
> ```

then install dependencies:
```
pip3 install -r requirements-dev.txt
```

Running a Open TZ web server 
```
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### Creating modules with Open TZ Command Line Tool (open_tz_cli)

To create a new module with Open Tz Command Line Tool you will need to run this command inside the project root folder:
```
python3 -m open_tz_cli create module_name
```

This will be created inside `plugins/{module_name}` inside the project root folder

To build this module run:
```
python3 -m open_tz_cli build path/to/module_name
```

for the case of default path it should be `plugins/{module_name}`

Then deploy this module in POST `/module` API
