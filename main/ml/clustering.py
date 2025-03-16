import pandas as pd
import numpy as np
import math
from sklearn.cluster import KMeans
import os
from django.conf import settings
import folium
def prepare_data_to_cluster(result_df):
    file_path = os.path.join(settings.BASE_DIR, "main", "static", "data", "cities_coordinates.csv")
    df_cities = pd.read_csv(file_path, encoding="utf-8-sig")
    merged_df = pd.merge(result_df, df_cities, on="city", how="left")
    order_df=merged_df.groupby(['file_date','customer']).agg(
        total_kg=('total_kg','sum'),
        city=('city','first'),
        Latitude=('latitude','first'),
        Longitude=('longitude','first')).reset_index()
    order_df["file_date"] = pd.to_datetime(order_df["file_date"], unit="s").dt.strftime("%Y-%m-%d")

    order_df=order_df.dropna()
    return order_df



def haversine(lat1, lon1, lat2, lon2):
    """
    מחשבת את המרחק בקילומטרים בין שתי נקודות גיאוגרפיות
    באמצעות נוסחת Haversine.
    """
    R = 6371  # רדיוס כדור הארץ בקילומטרים
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# פונקציה לחישוב מרחק גיאוגרפי בין קלאסטרים
def compute_geographical_distance(centroids):
    distances = np.zeros((len(centroids), len(centroids)))
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            lat1, lon1 = centroids[i]
            lat2, lon2 = centroids[j]
            dlat = np.radians(lat2 - lat1)
            dlon = np.radians(lon2 - lon1)
            a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
            distance = 6371 * c  # קילומטרים
            distances[i, j] = distance
            distances[j, i] = distance
    return distances

def transfer_orders(order_df, clusters, centroids, max_weight=6000, max_increment=1000):
    cluster_weights = {i: 0 for i in range(len(set(clusters)))}
    
    # שמירה על האינדקסים המקוריים של הדאטה
    order_df = order_df.reset_index(drop=True)  # וודא שאינדקסים מסודרים מחדש
    
    # עדכון משקלות של קלאסטרים
    for i, cluster in enumerate(clusters):
        cluster_weights[cluster] += order_df['total_kg'].iloc[i]

    overweight_clusters = [cluster for cluster, weight in cluster_weights.items() if weight > max_weight]
    
    print(f"🔎 קלאסטרים עם משקל עודף: {overweight_clusters}")

    iteration = 0
    while overweight_clusters:
        iteration += 1
        print(f"🔄 איטרציה מספר {iteration} - {overweight_clusters}")

        unable_to_move = True  # דגל שמוודא אם הצלחנו להעביר לפחות אחת מההזמנות

        for overweight_cluster in overweight_clusters:
            overweight_orders = order_df[clusters == overweight_cluster]
            print(f"📌 מעבד קלאסטר {overweight_cluster} עם {len(overweight_orders)} הזמנות")

            overweight_orders = overweight_orders.sort_values(by='total_kg')

            for i, row in overweight_orders.iterrows():
                if cluster_weights[overweight_cluster] > max_weight:
                    distances = compute_geographical_distance(centroids)
                    close_clusters = np.argsort(distances[overweight_cluster])
                    
                    for cluster in close_clusters:
                        if cluster != overweight_cluster:
                            if cluster_weights[cluster] + row['total_kg'] <= max_weight:
                                print(f"✅ מעביר הזמנה {i} מקלאסטר {overweight_cluster} ל-{cluster}")

                                clusters[i] = cluster  # עדכון קלאסטר
                                cluster_weights[cluster] += row['total_kg']
                                cluster_weights[overweight_cluster] -= row['total_kg']
                                unable_to_move = False  # הצלחנו להזיז לפחות משהו
                                break
                        else:
                            print(f"⚠️ לא נמצא קלאסטר מתאים להזזה עבור {i}")

        # אם לא הצלחנו להזיז כלום, נעלה את המשקל המקסימלי
        if unable_to_move:
            max_weight += max_increment
            print(f"⚠️ לא ניתן היה לחלק את כל הקלאסטרים. מגבלת המשקל עלתה ל-{max_weight}")

        # עדכון של המשקל לכל קלאסטר
        cluster_weights = {i: 0 for i in range(len(set(clusters)))}
        for i, cluster in enumerate(clusters):
            cluster_weights[cluster] += order_df['total_kg'].iloc[i]

        overweight_clusters = [cluster for cluster, weight in cluster_weights.items() if weight > max_weight]

        if iteration > 20:  # עצירה מניעתית ללולאה אינסופית
            print("❌ עצירה: יותר מדי איטרציות בלולאת ההעברה!")
            break

    return clusters




def redistribute_clusters(order_df, clusters, centroids, max_weight=6000, max_distance=50):
    # שימו לב ששינוי האינדקסים בתוצאה יכול לגרום לבעיה בעת העדכון
    # לכן חשוב להימנע משימוש ישיר במערך clusters
    cluster_weights = {i: 0 for i in range(len(set(clusters)))}
    
    # וודא שעדכנו את האינדקסים של הדאטה לפני כל שינוי
    order_df = order_df.reset_index(drop=True)
    
    # עדכון משקולות
    for i, cluster in enumerate(clusters):
        cluster_weights[cluster] += order_df['total_kg'].iloc[i]

    sorted_clusters = sorted(cluster_weights.items(), key=lambda x: x[1])

    for cluster_to_remove, weight in sorted_clusters:
        if weight == 0:
            continue
        orders_to_reassign = order_df[clusters == cluster_to_remove]

        original_clusters = clusters.copy()
        success = True

        for i, row in orders_to_reassign.iterrows():
            distances = [
                haversine(row['Latitude'], row['Longitude'], centroids[target_cluster][0], centroids[target_cluster][1])
                for target_cluster in range(len(centroids))
            ]
            sorted_cluster_indices = np.argsort(distances)

            transferred = False
            for target_cluster in sorted_cluster_indices:
                if target_cluster == cluster_to_remove:
                    continue
                # בדיקת מגבלת משקל ומרחק
                if cluster_weights[target_cluster] + row['total_kg'] <= max_weight and distances[target_cluster] <= max_distance:
                    clusters[i] = target_cluster  # עדכון עם קלאסטר חדש
                    cluster_weights[target_cluster] += row['total_kg']
                    cluster_weights[cluster_to_remove] -= row['total_kg']
                    transferred = True
                    break

            if not transferred:
                success = False
                break

        if not success:
            clusters = original_clusters  # אם לא הצלחנו - שוחזר את הקלאסטרים הקודמים
            break

    return clusters


# פונקציה לעיבוד הנתונים עבור תאריך ספציפי
def process_orders_by_date(order_df):
    # סינון נתונים לפי תאריך
    order_filtered = order_df
    print(order_filtered)
    print(order_filtered[['Latitude', 'Longitude']].dtypes)

    try:
        print(f"📊 רץ KMeans עם {order_filtered.shape[0]} שורות")
        kmeans = KMeans(n_clusters=5, random_state=42)
        initial_clusters = kmeans.fit_predict(order_filtered[['Latitude', 'Longitude']])
        centroids = kmeans.cluster_centers_
        print(f"✅ KMeans הסתיים בהצלחה!")
    except Exception as e:
        print(f"❌ שגיאה ב-KMeans: {e}")

    print(f"📊 לפני העברת הזמנות: {np.unique(initial_clusters, return_counts=True)}")

    # הפעלת הפונקציות להעברת הזמנות וסידור מחדש של קלאסטרים
    try:
        final_clusters = transfer_orders(order_filtered, initial_clusters, centroids)
        print(f"✅ העברת ההזמנות הסתיימה בהצלחה!")
    except Exception as e:
        print(f"❌ שגיאה ב-transfer_orders: {e}")


    final_clusters = redistribute_clusters(order_filtered, final_clusters, centroids)

    # החזרת התוצאות עם העמודה Cluster
    order_filtered['Cluster'] = final_clusters
    return order_filtered,order_filtered[['Latitude', 'Longitude', 'total_kg', 'Cluster']].groupby('Cluster').sum()



def generate_maps(order_filtered):
    """
    פונקציה ליצירת שתי מפות:
    1. מפה בסיסית עם כלל הנקודות.
    2. מפה עם צבעים לפי קלאסטרים.
    
    :param order_filtered: DataFrame עם נתוני ההזמנות (Latitude, Longitude, Cluster)
    :return: קוד HTML של המפות להצגה ב-Django
    """
    

    # יצירת מפה שנייה עם צבעים לפי קלאסטרים
    map2 = folium.Map(location=[32.0853, 34.7818], zoom_start=12)

    # הוספת כותרת למפה
    folium.Marker([33.2, 34.7818], popup="מפה לפי קלאסטרים").add_to(map2)

    # צבעים מותאמים אישית לכל קלאסטר
    cluster_colors = {
        cluster: color for cluster, color in zip(order_filtered['Cluster'].unique(), ['red', 'blue', 'green', 'purple', 'orange'])
    }

    # הוספת כל נקודה עם צבעים לפי קלאסטר
    for _, row in order_filtered.iterrows():
        cluster_color = cluster_colors.get(row['Cluster'], 'gray')

        folium.CircleMarker(
            location=[row['Latitude'], row['Longitude']],
            radius=5,
            color=cluster_color,
            fill=True,
            fill_color=cluster_color
        ).add_to(map2)

    # המרות ל-HTML עבור Django
    
    map2_html = map2._repr_html_()

    return  map2_html
