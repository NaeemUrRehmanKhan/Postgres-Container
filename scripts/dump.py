import csv
import os
import psycopg2

PGHOST = os.environ["PGHOST"]
PGUSER = os.environ["PGUSER"]
PGPASSWORD = os.environ["PGPASSWORD"]
PGDATABASE = os.environ["PGDATABASE"]

OUTPUT = "/tmp/repos.csv"

def main():
    conn = psycopg2.connect(
        host=PGHOST, user=PGUSER, password=PGPASSWORD, dbname=PGDATABASE
    )
    cur = conn.cursor()

    cur.execute("SELECT repo_id, name, stars, fetched_at FROM repos ORDER BY stars DESC")

    rows = cur.fetchall()

    with open(OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["repo_id", "name", "stars", "fetched_at"])
        writer.writerows(rows)

    print(f"CSV saved to {OUTPUT}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()