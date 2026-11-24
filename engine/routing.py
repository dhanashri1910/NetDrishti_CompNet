
"""Simplified path finding with lowest-cost route recommendation.
Keeps the existing Bellman-Ford and Dijkstra functions for compatibility.
"""

import heapq

INF = float("inf")


def build_graph(nodes, edges, fail=()):
    """Build an undirected weighted network graph."""
    down = {frozenset(k.split("-")) for k in fail}
    graph = {n: {} for n in nodes}

    for edge in edges:
        a, b = edge["a"], edge["b"]
        cost = float(edge["cost"])

        if edge.get("up", True) is False:
            continue

        if frozenset((a, b)) in down:
            continue

        if a not in graph or b not in graph:
            continue

        graph[a][b] = cost
        graph[b][a] = cost

    return graph


def bellman_ford(g, src):
    dist = {n: INF for n in g}
    prev = {n: None for n in g}

    dist[src] = 0
    passes = 0
    relax = 0

    for _ in range(len(g) - 1):
        changed = False
        passes += 1

        for u in g:
            for v, w in g[u].items():
                relax += 1

                if dist[u] != INF and dist[u] + w < dist[v]:
                    dist[v] = dist[u] + w
                    prev[v] = u
                    changed = True

        if not changed:
            break

    return dist, prev, {
        "passes": passes,
        "relaxations": relax
    }


def dijkstra(g, src):
    dist = {n: INF for n in g}
    prev = {n: None for n in g}

    dist[src] = 0
    pq = [(0, src)]
    pops = 0

    while pq:
        d, u = heapq.heappop(pq)
        pops += 1

        if d > dist[u]:
            continue

        for v, w in g[u].items():
            if d + w < dist[v]:
                dist[v] = d + w
                prev[v] = u
                heapq.heappush(pq, (dist[v], v))

    return dist, prev, {"heap_pops": pops}


def path_of(prev, src, dst):
    path = []
    node = dst

    while node is not None:
        path.append(node)
        node = prev[node]

    path.reverse()

    return path if path and path[0] == src else []


def table(g, src, algo):
    algorithm = bellman_ford if algo == "bellman-ford" else dijkstra

    dist, prev, work = algorithm(g, src)
    rows = []

    for destination in sorted(g):
        if destination == src:
            continue

        path = path_of(prev, src, destination)

        rows.append({
            "dest": destination,
            "next_hop": path[1] if len(path) > 1 else None,
            "cost": None if dist[destination] == INF else dist[destination],
            "hops": len(path) - 1 if path else None,
            "path": path
        })

    return rows, work


def find_all_paths(g, src, dst, limit=200):
    """
    Find all simple paths between source and destination.
    A simple path does not visit the same device twice.
    Results are sorted from lowest cost to highest cost.
    """

    if src not in g or dst not in g:
        return []

    if src == dst:
        return [{
            "path": [src],
            "cost": 0,
            "hops": 0
        }]

    results = []

    def search(current, path, total_cost):
        if len(results) >= limit:
            return

        if current == dst:
            results.append({
                "path": path[:],
                "cost": round(total_cost, 2),
                "hops": len(path) - 1
            })
            return

        for neighbour, cost in g[current].items():

            # Avoid visiting the same device twice
            if neighbour in path:
                continue

            search(
                neighbour,
                path + [neighbour],
                total_cost + cost
            )

    search(src, [src], 0)

    results.sort(
        key=lambda item: (
            item["cost"],
            item["hops"],
            item["path"]
        )
    )

    return results


def alternatives(g, src, dst, algo="dijkstra", limit=3):
    """Return alternative routes excluding the best route."""

    paths = find_all_paths(g, src, dst, limit=limit + 1)

    return paths[1:limit + 1]


def compute(nodes, edges, src, dst, fail=()):
    """
    Calculate routing results before and after link failures.
    Also provides all possible paths and the cheapest path.
    """

    out = {}

    for fail_set, label in (
        ((), "before"),
        (tuple(fail), "after")
    ):

        if label == "after" and not fail:
            break

        graph = build_graph(nodes, edges, fail_set)

        result = {}

        for algo in ("bellman-ford", "dijkstra"):
            rows, work = table(graph, src, algo)

            row = next(
                (r for r in rows if r["dest"] == dst),
                None
            )

            result[algo] = {
                "table": rows,
                "work": work,
                "route": row
            }

        # Find all possible routes
        all_paths = find_all_paths(graph, src, dst)

        # Cheapest route
        best_path = all_paths[0] if all_paths else None

        result["all_paths"] = all_paths
        result["best_path"] = best_path

        result["alternatives"] = alternatives(
            graph, src, dst
        )

        result["agree"] = (
            (result["bellman-ford"]["route"] or {}).get("cost")
            ==
            (result["dijkstra"]["route"] or {}).get("cost")
        )

        out[label] = result

    return out


DEMO = {
    "nodes": ["A", "B", "C", "D", "E", "F"],
    "edges": [
        {"a": "A", "b": "B", "cost": 2},
        {"a": "A", "b": "C", "cost": 5},
        {"a": "B", "b": "C", "cost": 1},
        {"a": "B", "b": "D", "cost": 4},
        {"a": "C", "b": "D", "cost": 2},
        {"a": "C", "b": "E", "cost": 6},
        {"a": "D", "b": "F", "cost": 3},
        {"a": "E", "b": "F", "cost": 1},
        {"a": "D", "b": "E", "cost": 5}
    ]
}
