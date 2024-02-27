# TODO: could not resolve dependencies with alpine or slim version, consider changing to alpine after creating requirements.txt with pip freeze
FROM python:3.12 as python-base 
WORKDIR /home
RUN pip3 install --upgrade pip
COPY ./requirements.txt .
RUN pip3 install -r requirements.txt
FROM python-base as cached-modules
COPY . .
ENTRYPOINT [ "python3", "main.py" ]
