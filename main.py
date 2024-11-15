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
    return FileResponse("./templates/home.html")


@app.get("/tailwind.css")
def styles():
    return FileResponse("./tailwind.css")


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

    cur = connection.cursor()

    cur.execute(
        """
        SELECT count(*) FROM Highlight
        WHERE visitor = %s AND county = %s;
      """,
        (userId, fips_code),
    )

    if cur.fetchall()[0][0] > 0:
        cur.close()
        return HTMLResponse("Highlighted")

    cur.close()
    return HTMLResponse("Not Highlighted")


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
    state_matching_elections: int
    state_total_elections: int
    favorited: bool
    results: list[list]
    state_results: list[list]
    demographics: list[float]


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

    cur1 = connection.cursor()
    cur1.execute(
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

    cur2 = connection.cursor()
    cur2.execute(
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

    cur3 = connection.cursor()
    cur3.execute(
        """
SELECT 
    e.year_num AS "election year",
    100.0 * cr.D_votes / (cr.D_votes + cr.R_votes) AS "county D",
    100.0 * cr.R_votes / (cr.D_votes + cr.R_votes) AS "county R",
    cr.winner AS "county winner",
    100.0 * e.D_votes / (e.D_votes + e.R_votes) AS "national D",
    100.0 * e.R_votes / (e.D_votes + e.R_votes) AS "national R",
    e.winner AS "national winner",
    cr.winner = e.winner as "match?"
FROM 
    Election e
JOIN 
    County_Result cr ON e.year_num = cr.election
WHERE 
    cr.county = %s
ORDER BY e.year_num DESC;
        """,
        (fips_code,),
    )

    cur4 = connection.cursor()
    cur4.execute(
        """
SELECT 
    pct_white * 100,
    pct_black * 100,
    pct_asian * 100,
    pct_hisp * 100
FROM 
    County_Demographics
WHERE 
    county = %s AND census_year = 2020;
        """,
        (fips_code,),
    )

    cur5 = connection.cursor()
    cur5.execute(
        """
SELECT 
    sr.election AS "election year",
    100.0 * cr.D_votes / (cr.D_votes + cr.R_votes) AS "county D",
    100.0 * cr.R_votes / (cr.D_votes + cr.R_votes) AS "county R",
    cr.winner AS "county winner",
    100.0 * sr.D_votes / (sr.D_votes + sr.R_votes) AS "state D",
    100.0 * sr.R_votes / (sr.D_votes + sr.R_votes) AS "state R",
    sr.winner AS "state winner",
    cr.winner = sr.winner AS "match?"
FROM 
    State_Result sr
LEFT JOIN 
    County_Result cr ON sr.election = cr.election 
                     AND cr.county IN (SELECT fips_code FROM County WHERE state = sr.state)
WHERE 
    cr.county = %s
ORDER BY 
    sr.election DESC;
        """,
        (fips_code,),
    )

    results_1: list = cur1.fetchall()[0]  # type: ignore (trust me bro)
    results_2: list[int] = cur2.fetchall()[0]  # type: ignore (trust me bro)
    results_3: list[list] = cur3.fetchall()  # type: ignore (trust me bro)
    results_4: list[float] = cur4.fetchall()[0]  # type: ignore (trust me bro)
    results_5: list[list] = cur5.fetchall()  # type: ignore (trust me bro)

    cur1.close()
    cur2.close()
    cur3.close()
    cur4.close()
    cur5.close()

    state_matches = sum([result[7] for result in results_5])
    state_total = len(results_5)

    county = County(
        fips=results_1[0],
        name=results_1[1],
        state=results_1[2],
        favorited=results_1[3],
        matching_elections=results_2[0],
        total_elections=results_2[1],
        results=results_3,
        state_results=results_5,
        state_matching_elections=state_matches,
        state_total_elections=state_total,
        demographics=results_4,
    )

    return HTMLResponse(template.render(county=county))
