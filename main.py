from fastapi import FastAPI
import psycopg2
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from jinja2 import Environment, PackageLoader, select_autoescape
from dotenv import load_dotenv

from dataclasses import dataclass

import os

app = FastAPI()

load_dotenv()

# TODO: make these environment variables
connection = psycopg2.connect(
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
)

jinja_env = Environment(loader=PackageLoader("main"), autoescape=select_autoescape())


@app.get("/")
def root():
    return FileResponse("./pages/home.html")


@app.get("/counties")
def get_counties(user_id: str | None = None, search_term: str = ""):
    cur = connection.cursor()

    cur.execute(
        "SELECT fips_code, name, state FROM county where name ILIKE %s;",
        (f"%{search_term}%",),
    )
    results = cur.fetchall()
    cur.close()

    template = jinja_env.get_template("county_table.html")

    return HTMLResponse(template.render(counties=results))


@dataclass
class County:
    name: str
    state: str
    fips: str
    matching_elections: int
    total_elections: int


@app.get("/county/{fips_code}")
def county_page(fips_code: str):
    template = jinja_env.get_template("county_page.html")

    cur = connection.cursor()

    cur.execute(
        "SELECT fips_code, name, state FROM county where fips_code = %s;", (fips_code,)
    )

    results_1: list[str] = cur.fetchall()[0]  # type: ignore (trust me bro)

    cur.execute(
        """
SELECT 
    COUNT(DISTINCT CASE 
                    WHEN county_result.winner = election.winner THEN election.year_num 
                    ELSE NULL 
                  END) AS matching_elections,
    COUNT(DISTINCT election) AS total_elections
FROM 
    County_Result county_result
JOIN 
    Election election ON county_result.election = election.year_num
WHERE 
    county_result.county = %s;
""",
        (fips_code,),
    )

    results_2: list[int] = cur.fetchall()[0]  # type: ignore (trust me bro)

    cur.close()

    county = County(
        fips=results_1[0],
        name=results_1[1],
        state=results_1[2],
        matching_elections=results_2[0],
        total_elections=results_2[1],
    )

    return HTMLResponse(template.render(county=county))
