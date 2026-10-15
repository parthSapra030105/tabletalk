import pytest

from agent.sqlguard import ROW_CAP, QueryRejected, check

CATALOG = {
    "schema": "ds_1",
    "tables": [
        {"name": "orders", "columns": [{"name": n} for n in
                                       ["order_id", "order_date", "cust_id", "region", "net_amount", "gross_amount", "status"]]},
        {"name": "customers", "columns": [{"name": n} for n in ["customerid", "city", "segment"]]},
    ],
}


@pytest.mark.parametrize("sql", [
    "SELECT region, SUM(net_amount) FROM orders GROUP BY region",
    "select count(*) from orders where status = 'Cancelled'",
    "SELECT c.city, SUM(o.net_amount) AS revenue FROM orders o JOIN customers c ON c.customerid = o.cust_id "
    "GROUP BY c.city ORDER BY revenue DESC",
    "WITH m AS (SELECT date_trunc('month', order_date) AS month, SUM(net_amount) AS total FROM orders GROUP BY 1) "
    "SELECT month, total, total - LAG(total) OVER (ORDER BY month) AS change FROM m",
    "SELECT region FROM orders UNION SELECT city FROM customers",
    "SELECT EXTRACT(YEAR FROM order_date) AS y, COUNT(*) FROM orders GROUP BY y",
    "SELECT * FROM (SELECT region, net_amount FROM orders) s WHERE s.net_amount > 50000",
    "SELECT CASE WHEN net_amount > 1000 THEN 'big' ELSE 'small' END AS size, COUNT(*) FROM orders GROUP BY 1",
    "SELECT ds_1.orders.region FROM ds_1.orders",
    "SELECT COALESCE(region, 'unknown') FROM orders",
])
def test_reads_are_allowed(sql):
    assert check(sql, CATALOG).sql


@pytest.mark.parametrize("sql, reason", [
    ("DELETE FROM orders WHERE status = 'Cancelled'", "only select"),
    ("UPDATE orders SET net_amount = 0", "only select"),
    ("INSERT INTO orders (order_id) VALUES ('x')", "only select"),
    ("DROP TABLE orders", "only select"),
    ("TRUNCATE orders", "only select"),
    ("ALTER TABLE orders ADD COLUMN x int", "only select"),
    ("CREATE TABLE evil AS SELECT * FROM orders", "only select"),
    ("SELECT * FROM orders; UPDATE orders SET net_amount = 0", "exactly one"),
    ("SELECT 1; DROP TABLE orders", "exactly one"),
    ("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d", "delete"),
    ("SELECT * INTO stolen FROM orders", "into"),
    ("SELECT * FROM orders FOR UPDATE", "lock"),
    ("SET statement_timeout = 0", "only select"),
    ("COPY orders TO '/tmp/orders.csv'", "only select"),
    ("GRANT ALL ON orders TO PUBLIC", "only select"),
    ("VACUUM orders", "only select"),
    ("SELECT pg_sleep(60)", "pg_sleep"),
    ("SELECT region FROM orders WHERE pg_sleep(60) IS NOT NULL", "pg_sleep"),
    ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT set_config('statement_timeout', '0', false)", "set_config"),
    ("SELECT * FROM dblink('host=evil', 'SELECT 1') AS t(x int)", "dblink"),
    ("SELECT * FROM pg_catalog.pg_roles", "outside"),
    ("SELECT * FROM information_schema.tables", "outside"),
    ("SELECT * FROM ds_2.orders", "outside"),
    ("SELECT * FROM public.app_secret", "outside"),
    ("SELECT * FROM payments", "unknown table"),
    ("SELECT profit FROM orders", "unknown column"),
    ("SELECT o.city FROM orders o", "unknown column"),
    ("", "empty"),
    ("this is not sql at all", ""),
])
def test_everything_else_is_rejected(sql, reason):
    with pytest.raises(QueryRejected) as e:
        check(sql, CATALOG)
    assert reason in str(e.value).lower()


def test_limit_is_added_when_missing():
    assert check("SELECT region FROM orders", CATALOG).sql.endswith(f"LIMIT {ROW_CAP + 1}")


def test_limit_is_tightened_when_too_big():
    assert check("SELECT region FROM orders LIMIT 5000000", CATALOG).sql.endswith(f"LIMIT {ROW_CAP + 1}")


def test_small_limit_is_kept():
    assert check("SELECT region FROM orders ORDER BY net_amount DESC LIMIT 10", CATALOG).sql.endswith("LIMIT 10")


def test_union_gets_a_limit_too():
    assert f"LIMIT {ROW_CAP + 1}" in check("SELECT region FROM orders UNION SELECT city FROM customers", CATALOG).sql


def test_tables_used_are_reported():
    q = check("SELECT c.city FROM orders o JOIN customers c ON c.customerid = o.cust_id", CATALOG)
    assert q.tables == ["customers", "orders"]
