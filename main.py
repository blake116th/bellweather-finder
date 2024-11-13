from fastapi import Cookie, FastAPI
from typing import Annotated

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


@app.get("/favicon.ico")
def favicon():
    return FileResponse("./favicon.ico")


@app.put("/county/{fips_code}/favorite")
def favorite(
    fips_code: str,
    userId: Annotated[str | None, Cookie()] = None,  # type: ignore
):
    print("fips", fips_code, "userId", userId)

    if userId == None:
        return 400

    cur = connection.cursor()

    try:
        # toggle row
        cur.execute(
            """
      WITH ins AS (
          INSERT INTO Highlight (visitor, county)
          VALUES (%(visitor)s, %(county)s)
          ON CONFLICT (visitor, county) DO NOTHING
          RETURNING *
      )
      DELETE FROM Highlight
      WHERE visitor = %(visitor)s AND county = %(county)s AND NOT EXISTS (SELECT 1 FROM ins);
      """,
            {"visitor": userId, "county": fips_code},
        )
    except:
        connection.rollback()
        cur.close()
        return 500

    cur.close()

    connection.commit()

    return HTMLResponse("favorited")


@app.get("/counties")
def get_counties(user_id: str | None = None, search_term: str = ""):
    cur = connection.cursor()

    print(user_id)

    cur.execute(
        """
            SELECT 
                c.fips_code, 
                c.name, 
                c.state,
                CASE 
                    WHEN h.visitor IS NOT NULL THEN TRUE 
                    ELSE FALSE 
                END AS highlighted
            FROM 
                County c
            LEFT JOIN 
                Highlight h ON c.fips_code = h.county AND h.visitor = %s
            WHERE 
                c.name ILIKE %s
            ORDER BY highlighted DESC;""",
        (user_id, f"%{search_term}%"),
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
    favorited: bool


@app.put("/id/{id}")
def put_id(id: str):
    cur = connection.cursor()

    cur.execute(
        """
        INSERT INTO Visitor (uuid)
        VALUES (%s)
        ON CONFLICT (uuid) DO NOTHING;
        """,
        (id,),
    )

    cur.close()

    connection.commit()

    return


@app.get("/county/{fips_code}")
def county_page(
    fips_code: str,  # --
    userId: Annotated[str | None, Cookie()] = None,  # type: ignore
):
    print("cookie", userId)
    template = jinja_env.get_template("county_page.html")

    cur = connection.cursor()

    cur.execute(
        """SELECT 
            c.fips_code,
            c.name, 
            c.state,
            CASE 
                WHEN h.visitor IS NOT NULL THEN TRUE 
                ELSE FALSE 
            END AS highlighted
          FROM 
            county c
          LEFT JOIN 
            Highlight h ON c.fips_code = h.county AND h.visitor = %s
          WHERE fips_code = %s;
          """,
        (userId, fips_code),
    )

    results_1: list = cur.fetchall()[0]  # type: ignore (trust me bro)

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
        favorited=results_1[3],
        matching_elections=results_2[0],
        total_elections=results_2[1],
    )

    return HTMLResponse(template.render(county=county))
