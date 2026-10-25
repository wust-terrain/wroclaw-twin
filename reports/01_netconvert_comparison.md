# Task 01: our signal clusters vs netconvert traffic lights

Net: `/tmp/r123_join.net.xml` (1332 junctions of type `traffic_light`, built with `--junctions.join --tls.join`). Our clusters: 900 (single linkage, eps 20 m). The netconvert count comes from a topological join, a different method, and is not a ground truth.

A traffic light belongs to the cluster of the nearest signal node if it lies within eps = 20 m of it. 13 of 1332 have no signal node that close (distance to nearest signal node: median 0.0 m, p90 10.1 m).

## Our clusters by number of netconvert traffic lights inside

| TLs in cluster | our clusters |
|---|---|
| 0 | 168 |
| 1 | 446 |
| 2+ | 286 |

## Distribution of traffic lights per cluster

| TLs | clusters |
|---|---|
| 0 | 168 |
| 1 | 446 |
| 2 | 152 |
| 3 | 66 |
| 4 | 33 |
| 5 | 16 |
| 6 | 7 |
| 7 | 1 |
| 8 | 6 |
| 9 | 1 |
| 10 | 1 |
| 12 | 1 |
| 15 | 1 |
| 16 | 1 |

## 10 clusters with the most netconvert traffic lights

| cluster_id | TLs | n_nodes | x [m, 2177] | y [m, 2177] | lon | lat |
|---|---|---|---|---|---|---|
| 1 | 16 | 16 | 6428510.9 | 5662668.2 | 16.97944 | 51.09459 |
| 230 | 15 | 17 | 6429700.9 | 5658960.8 | 16.99714 | 51.06141 |
| 361 | 12 | 12 | 6433724.1 | 5663232.8 | 17.05374 | 51.10029 |
| 67 | 10 | 10 | 6432711.5 | 5664407.4 | 17.03907 | 51.11073 |
| 37 | 9 | 12 | 6434541.5 | 5666736.9 | 17.06478 | 51.13188 |
| 18 | 8 | 14 | 6431882.8 | 5664514.1 | 17.02722 | 51.11159 |
| 40 | 8 | 8 | 6431960.7 | 5666908.1 | 17.02788 | 51.13312 |
| 71 | 8 | 10 | 6427717.9 | 5658259.4 | 16.96900 | 51.05486 |
| 268 | 8 | 8 | 6429582.0 | 5666195.3 | 16.99404 | 51.12642 |
| 288 | 8 | 8 | 6432915.8 | 5665318.5 | 17.04182 | 51.11894 |

Run time: 12.2 s
