import os
import requests
import psycopg2
from psycopg2.extras import execute_batch
import time

GITHUB_API = "https://api.github.com/graphql"
TOKEN = os.environ["GITHUB_TOKEN"]

PGHOST = os.environ["PGHOST"]
PGUSER = os.environ["PGUSER"]
PGPASSWORD = os.environ["PGPASSWORD"]
PGDATABASE = os.environ["PGDATABASE"]


def graphql_query(search_query, cursor):
    return f"""
    query {{
      search(type: REPOSITORY, query: "{search_query}", first: 100, after: {cursor}) {{
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


def fetch_batch(search_query, cursor):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    body = {"query": graphql_query(search_query, f'"{cursor}"' if cursor else "null")}

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


def fetch_for_query(search_query, max_records=1000):
    """Fetch repositories for a specific search query (max 1000 due to GitHub limit)"""
    cursor = None
    fetched = 0

    while fetched < max_records:
        print(f"  Fetching batch for '{search_query}'... {fetched} so far")
        
        try:
            data = fetch_batch(search_query, cursor)
        except Exception as e:
            print(f"  Error fetching: {e}")
            break

        if not data["edges"]:
            break

        rows = []
        for edge in data["edges"]:
            repo = edge["node"]
            rows.append((repo["id"], repo["nameWithOwner"], repo["stargazerCount"]))

        insert_into_db(rows)

        fetched += len(rows)
        cursor = data["pageInfo"]["endCursor"]

        if not data["pageInfo"]["hasNextPage"]:
            print(f"  Completed '{search_query}': {fetched} records")
            break
        
        time.sleep(0.5)  # Rate limiting

    return fetched


def main():
    # Define star ranges to break the 1000-result limit
    star_ranges = [
        "stars:100000..*",      # 100k+ stars
        "stars:50000..99999",   # 50k-100k stars
        "stars:20000..49999",   # 20k-50k stars
        "stars:10000..19999",   # 10k-20k stars
        "stars:5000..9999",     # 5k-10k stars
        "stars:2000..4999",     # 2k-5k stars
        "stars:1000..1999",     # 1k-2k stars
        "stars:500..999",       # 500-1k stars
        "stars:200..499",       # 200-500 stars
        "stars:100..199",       # 100-200 stars
        "stars:50..99",         # 50-100 stars
        "stars:20..49",         # 20-50 stars
        "stars:10..19",         # 10-20 stars
        "stars:5..9",           # 5-10 stars
        "stars:1..4",           # 1-5 stars
    ]

    total_fetched = 0

    for search_query in star_ranges:
        print(f"\nFetching repositories: {search_query}")
        count = fetch_for_query(search_query, max_records=1000)
        total_fetched += count
        
        print(f"Total fetched across all queries: {total_fetched}\n")

    print(f"✓ Completed! Total records: {total_fetched}")


if __name__ == "__main__":
    main()