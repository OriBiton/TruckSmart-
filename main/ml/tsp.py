import pandas as pd
import numpy as np
import requests
import folium
import polyline
import random
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

# נקודת ההתחלה (אזור התעשייה ברקן)
start_point = {"Latitude": 32.11819, "Longitude": 35.12345}

# פונקציה לקבלת מטריצת מרחקים מגוגל

import requests
import time
import math

import requests
import time
import math

def get_distance_matrix(origins, destinations, api_key, batch_size=25):
    """
    שולח בקשות למטריצת מרחקים בחבילות קטנות כדי לא לעבור את המגבלה של גוגל (625 אלמנטים).
    
    :param origins: רשימת מקורות (lat, lon)
    :param destinations: רשימת יעדים (lat, lon)
    :param api_key: מפתח API
    :param batch_size: מספר מקורות/יעדים בכל חבילה (ברירת מחדל 25)
    :return: רשימת תוצאות מטריצת המרחקים
    """
    url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters"
    }
    
    results = []
    total_origin_batches = math.ceil(len(origins) / batch_size)
    total_destination_batches = math.ceil(len(destinations) / batch_size)

    for i in range(total_origin_batches):
        start_origin_idx = i * batch_size
        end_origin_idx = min((i + 1) * batch_size, len(origins))
        batch_origins = origins[start_origin_idx:end_origin_idx]

        for j in range(total_destination_batches):
            start_dest_idx = j * batch_size
            end_dest_idx = min((j + 1) * batch_size, len(destinations))
            batch_destinations = destinations[start_dest_idx:end_dest_idx]

            payload = {
                "origins": [{"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lon}}}} for lat, lon in batch_origins],
                "destinations": [{"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lon}}}} for lat, lon in batch_destinations],
                "travelMode": "DRIVE"
            }

            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                results.extend(response.json())
            else:
                print(f"⚠️ שגיאה בקבלת מטריצת מרחקים (חלק {i+1}/{total_origin_batches}, {j+1}/{total_destination_batches}): {response.json()}")
                return None

            time.sleep(0.5)  # הוספת השהייה קצרה כדי למנוע חסימות מצד גוגל

    return results



# פתרון בעיית המסלול האופטימלי (TSP)
def solve_tsp(distance_matrix):
    num_locations = len(distance_matrix)
    manager = pywrapcp.RoutingIndexManager(num_locations, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(distance_matrix[from_node][to_node])

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.seconds = 10  

    solution = routing.SolveWithParameters(search_parameters)

    if solution:
        route = []
        index = routing.Start(0)
        while not routing.IsEnd(index):
            route.append(manager.IndexToNode(index))
            index = solution.Value(routing.NextVar(index))
        route.append(manager.IndexToNode(index))
        return route
    else:
        print("⚠️ לא נמצא פתרון ל-TSP")
        return None
# פונקציה לקבלת המסלול המדויק מגוגל
def get_google_route_exact_order(route_points, api_key):
    base_url = "https://routes.googleapis.com/directions/v2:computeRoutes"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.polyline"
    }

    payload = {
        "origin": {"location": {"latLng": {"latitude": route_points[0][0], "longitude": route_points[0][1]}}},
        "destination": {"location": {"latLng": {"latitude": route_points[-1][0], "longitude": route_points[-1][1]}}},
        "intermediates": [{"location": {"latLng": {"latitude": lat, "longitude": lon}}} for lat, lon in route_points[1:-1]],
        "travelMode": "DRIVE"
    }

    response = requests.post(base_url, headers=headers, json=payload)
    if response.status_code == 200:
        route_data = response.json()
        return route_data["routes"][0]["polyline"]["encodedPolyline"]
    else:
        print("Error fetching route:", response.json())
        return None

# פונקציה ליצירת מפה לכל קלאסטר **ללא שמירה לקובץ**
def generate_cluster_map(cluster_id, locations, optimal_route, api_key):
    map_center = locations[optimal_route[0]]
    route_map = folium.Map(location=map_center, zoom_start=10)

    def jitter(lat, lon, scale=0.0005):
        return lat + random.uniform(-scale, scale), lon + random.uniform(-scale, scale)

    for i, point in enumerate(optimal_route):
        lat, lon = jitter(*locations[point])

        folium.Marker(
            location=(lat, lon),
            popup=f"תחנה {i+1}: נקודה {point}",
            tooltip=f"תחנה {i+1}",
            icon=folium.DivIcon(html=f'''
                <div style="font-size: 12pt; color: white; background-color: {'red' if i == 0 else 'green' if i < len(optimal_route) - 1 else 'black'}; 
                text-align: center; width: 25px; height: 25px; border-radius: 50%; line-height: 25px;">
                    {i+1}
                </div>
            ''')
        ).add_to(route_map)

    # **הוספת קו מסלול באמצעות גוגל API**
    encoded_polyline = get_google_route_exact_order([locations[i] for i in optimal_route], api_key)
    if encoded_polyline:
        route_coordinates = polyline.decode(encoded_polyline)
        folium.PolyLine(route_coordinates, color="blue", weight=4, opacity=0.7).add_to(route_map)

    return route_map._repr_html_()  # החזרת HTML ישירות


# פונקציה ראשית שמבצעת עיבוד לכל הקלאסטרים
def process_all_clusters(order_filtered, api_key):
    cluster_maps = {}
    cluster_tables = {}

    for cluster_id in order_filtered["Cluster"].unique():
        print(f"🔄 מעבד קלאסטר {cluster_id}...")

        cluster_data = order_filtered[order_filtered["Cluster"] == cluster_id]
        df = pd.DataFrame(cluster_data)

        locations = [(start_point["Latitude"], start_point["Longitude"])] + list(zip(df["Latitude"], df["Longitude"]))

        distance_matrix_data = get_distance_matrix(locations, locations, api_key)
        if not distance_matrix_data:
            print(f"⚠️ דילוג על קלאסטר {cluster_id} עקב כשל בקבלת מטריצת המרחקים")
            continue

        num_locations = len(locations)
        distance_matrix_np = np.full((num_locations, num_locations), np.inf)
        for entry in distance_matrix_data:
            origin = entry["originIndex"]
            destination = entry["destinationIndex"]
            distance = entry.get("distanceMeters", np.inf)
            distance_matrix_np[origin, destination] = distance

        optimal_route = solve_tsp(distance_matrix_np)
        if not optimal_route:
            print(f"⚠️ דילוג על קלאסטר {cluster_id} עקב חוסר פתרון ל-TSP")
            continue

        map_html = generate_cluster_map(cluster_id, locations, optimal_route,api_key)
        cluster_maps[cluster_id] = map_html

        ordered_df = df.iloc[[i - 1 for i in optimal_route if i > 0]].copy()
        ordered_df.insert(0, "מספר תחנה", range(1, len(ordered_df) + 1))
        cluster_tables[cluster_id] = ordered_df.to_html(classes="table table-striped")

    return cluster_maps, cluster_tables
