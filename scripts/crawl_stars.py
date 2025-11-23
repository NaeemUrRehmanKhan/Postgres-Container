import os
import requests
import psycopg2
from psycopg2.extras import execute_batch

GITHUB_API = "https://api.github.com/graphql"
TOKEN = os.environ["GITHUB_TOKEN"]

PGHOST = os.environ["PGHOST"]
PGUSER = os.environ["PGUSER"]
PGPASSWORD = os.environ["PGPASSWORD"]
PGDATABASE = os.environ["PGDATABASE"]


def graphql_query(cursor):
    return f"""
    query {{
      search(type: REPOSITORY, query: "stars:>0", first: 100, after: {cursor}) {{
        repositoryCount
        edges {{
          cursor
          node {{
            ... on Repository {{
              id
              nameWithOwner
              stargazerCount
            }}
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
    """


def fetch_batch(cursor):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    body = {"query": graphql_query(f'"{cursor}"' if cursor else "null")}

    r = requests.post(GITHUB_API, json=body, headers=headers)
    r.raise_for_status()
    return r.json()["data"]["search"]


def insert_into_db(rows):
    conn = psycopg2.connect(
        host=PGHOST, user=PGUSER, password=PGPASSWORD, dbname=PGDATABASE
    )
    cur = conn.cursor()

    execute_batch(
        cur,
        """
        INSERT INTO repos (repo_id, name, stars)
        VALUES (%s, %s, %s)
        ON CONFLICT (repo_id)
        DO UPDATE SET stars = EXCLUDED.stars, fetched_at = CURRENT_TIMESTAMP;
        """,
        rows,
        page_size=100,
    )

    conn.commit()
    cur.close()
    conn.close()


def main():
    cursor = None
    total_fetched = 0
    LIMIT = 100000

    while total_fetched < LIMIT:
        print(f"Fetching batch… total so far: {total_fetched}")
        data = fetch_batch(cursor)

        rows = []
        for edge in data["edges"]:
            repo = edge["node"]
            rows.append((repo["id"], repo["nameWithOwner"], repo["stargazerCount"]))

        insert_into_db(rows)

        total_fetched += len(rows)
        cursor = data["pageInfo"]["endCursor"]

        if not data["pageInfo"]["hasNextPage"]:
            print("No more pages.")
            break

    print(f"Completed. Total fetched: {total_fetched}")


if __name__ == "__main__":
    main()