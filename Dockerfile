FROM python:3.9.13

RUN pip install --upgrade pip

RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/usr/local POETRY_VERSION=$POETRY_VERSION python -

WORKDIR /code

COPY pyproject.toml poetry.lock ./

RUN poetry install

COPY . ./

CMD ["poetry", "run", "python", "-m", "main"]