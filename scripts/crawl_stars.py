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

        if rows:
            insert_into_db(rows)

        fetched += len(rows)
        cursor = data["pageInfo"]["endCursor"]

        if not data["pageInfo"]["hasNextPage"]:
            print(f"  Completed '{search_query}': {fetched} records")
            break
        
        time.sleep(0.5)  # Rate limiting

    return fetched


def generate_queries():
    """Generate queries split by creation date to get 100k+ repos"""
    queries = []
    
    # Split by year and month for maximum coverage
    years = range(2008, 2025)  # GitHub launched in 2008
    months = range(1, 13)
    
    for year in years:
        for month in months:
            # Calculate the last day of the month
            if month == 12:
                next_month = 1
                next_year = year + 1
            else:
                next_month = month + 1
                next_year = year
            
            start_date = f"{year}-{month:02d}-01"
            
            # Create date range for the entire month
            if month in [1, 3, 5, 7, 8, 10, 12]:
                end_date = f"{year}-{month:02d}-31"
            elif month in [4, 6, 9, 11]:
                end_date = f"{year}-{month:02d}-30"
            else:  # February
                if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                    end_date = f"{year}-{month:02d}-29"
                else:
                    end_date = f"{year}-{month:02d}-28"
            
            queries.append(f"created:{start_date}..{end_date}")
    
    return queries


def main():
    queries = generate_queries()
    
    print(f"Generated {len(queries)} queries to fetch repositories\n")
    
    total_fetched = 0
    TARGET = 100000

    for idx, search_query in enumerate(queries, 1):
        if total_fetched >= TARGET:
            print(f"\nTarget reached! ({total_fetched:,} records)")
            break
            
        print(f"\n[{idx}/{len(queries)}] Fetching: {search_query}")
        count = fetch_for_query(search_query, max_records=1000)
        total_fetched += count
        
        print(f"Total fetched so far: {total_fetched:,}")
        
        if total_fetched >= TARGET:
            print(f"\n Target reached! ({total_fetched:,} records)")
            break

    print(f"\n✓ Completed! Total records: {total_fetched:,}")


if __name__ == "__main__":
    main()