from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
import pandas as pd
from django.shortcuts import render
from .forms import UploadFileForm
from .ml.preprocessing import ExcelProcessor
import os
import pandas as pd
from django.shortcuts import render
from .forms import UploadFileForm
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from .ml.preprocessing import ExcelProcessor
from .ml.clustering import prepare_data_to_cluster,process_orders_by_date,generate_maps
from io import StringIO
import os
from .ml.tsp import process_all_clusters
from django.conf import settings

os.environ["LOKY_MAX_CPU_COUNT"] = "4"  # שימוש ב-4 ליבות פיזיות

# View לטיפול בהתחברות
def login_view(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("home")  # הפניה לדף הבית לאחר התחברות
        else:
            return render(request, "main/login.html", {"error": "Invalid username or password"})

    return render(request, "main/login.html")


# View לטיפול בהרשמה
def register_view(request):
    if request.method == "POST":
        username = request.POST["username"]
        password1 = request.POST["password1"]
        password2 = request.POST["password2"]

        if password1 != password2:
            return render(request, "main/register.html", {"error": "Passwords do not match"})

        if User.objects.filter(username=username).exists():
            return render(request, "main/register.html", {"error": "Username already taken"})

        user = User.objects.create_user(username=username, password=password1)
        user.save()
        login(request, user)  # התחברות אוטומטית לאחר יצירת המשתמש
        return redirect("home")

    return render(request, "main/register.html")


# View ליציאה מהחשבון
def logout_view(request):
    logout(request)
    return redirect("login")

from django.shortcuts import render

def home_view(request):
    return render(request, "main/home.html")

 # ודא שהמחלקה נמצאת בקובץ נפרד בשם excel_processor.py

def upload_file(request):
    if request.method == "POST":
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES["file"]
            file_path = default_storage.save(f"temp/{file.name}", ContentFile(file.read()))
            
            # עיבוד הקובץ
            processor = ExcelProcessor([default_storage.path(file_path)])
            result_df = processor.process_all()
            df = prepare_data_to_cluster(result_df)
            
            request.session['data_types'] = {col: str(dtype) for col, dtype in df.dtypes.items()}
            request.session["df"] = df.to_json()  # שמירת הנתונים בסשן

            return redirect("results")  # הפניה ישירות לעמוד התוצאות

    else:
        form = UploadFileForm()

    return render(request, "main/upload.html", {"form": form})


def results(request):
    data_json = request.session.get("df")
    if data_json:
        try:
            df = pd.read_json(data_json)  # טוען את הנתונים מהסשן
            table_html = df.to_html(classes="table table-striped table-hover")  # הוספת עיצוב Bootstrap
            return render(request, "main/results.html", {"table": table_html})
        except Exception as e:
            return render(request, "main/error.html", {"message": f"⚠️ שגיאה בעיבוד הנתונים: {str(e)}"})
    
    return render(request, "main/error.html", {"message": "⚠️ אין נתונים להצגה."})




def cluster_orders_view(request):
    data_json = request.session.get('df')
    
    
    print(f"📊 Debug: df from session - {data_json[:500] if data_json else 'No Data'}")  # בדיקת הנתונים בסשן

    if data_json:
        df = pd.read_json(data_json)
        data_types = request.session.get('data_types')
        # שחזור סוגי הנתונים
        for col, dtype_str in data_types.items():
            df[col] = df[col].astype(dtype_str)

        request.session['df'] = df.to_json()
        order_df=df

        date_to_process = order_df["file_date"].iloc[0]
        print(order_df["file_date"].iloc[0])
        print(order_df)
        print(f"📅 תאריך לעיבוד: {date_to_process}")
        print(f"🔎 האם קיימים נתונים? {order_df[order_df['file_date'] == date_to_process].shape}")
        print(order_df.isnull().sum())
        order_filtered,result = process_orders_by_date(order_df)
        print(order_filtered)
        print(result)
        # קריאה לפונקציה החדשה שמייצרת את המפות
        map2_html = generate_maps(order_filtered)
        request.session['data_types_order_filtered'] = {col: str(dtype) for col, dtype in order_filtered.dtypes.items()}
            # המרת DataFrame ל-JSON ושמירה בסשן
        request.session["order_filtered"] = order_filtered.to_json()

          # תאריך ראשון
        

        return render(request, "main/cluster_results.html", {
            "table": order_filtered.to_html(),
            "summary": result.to_html(),
            "map2_html": map2_html
        })
    
    return render(request, "main/error.html", {"message": "אין נתונים בסשן"})



def cluster_routes_view(request):
    """ 
    תצוגת Django המציגה את מסלולי ההפצה והמפות לכל קלאסטר.
    משתמשת בנתונים מהסשן ומייצרת מפות דינמיות ללא שמירה לקובץ.
    """
    # טעינת הנתונים מהסשן
    data_json = request.session.get('order_filtered')
    if not data_json:
        return render(request, "main/error.html", {"message": "⚠️ אין נתונים בסשן. יש להעלות קובץ קודם."})
    api_key = os.getenv("GOOGLE_API_KEY")
    print("🔐 Key Loaded?", bool(api_key), "| First 5 chars:", api_key[:5] if api_key else "NONE")

    try:
        # שחזור ה-DataFrame מסשן
        order_filtered = pd.read_json(data_json)

        # שחזור סוגי הנתונים
        data_types = request.session.get('data_types_order_filtered', {})
        for col, dtype_str in data_types.items():
            try:
                order_filtered[col] = order_filtered[col].astype(dtype_str)
            except Exception as e:
                print(f"⚠️ שגיאה בהמרת העמודה '{col}' לסוג הנתונים '{dtype_str}': {e}")
        print(order_filtered.head())
        # בדיקת קיום מפתח API
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            print('hi')
            return render(request, "main/error.html", {"message": "⚠️ GOOGLE_API_KEY לא מוגדר ב- settings.py"})

        # יצירת המפות והטבלאות
        cluster_maps, cluster_tables = process_all_clusters(order_filtered, api_key)

        # המרת הטבלאות ל-HTML מראש (כדי למנוע שגיאה ב-Template)
        cluster_tables_html = cluster_tables  # כבר קיבלת HTML, אין צורך להמיר שוב


        return render(request, "main/cluster_routes.html", {
            "cluster_maps": cluster_maps,
            "cluster_tables": cluster_tables_html  # שולחים את ה-HTML כבר מוכן
        })

    except Exception as e:
        print(f"⚠️ שגיאה בטעינת הנתונים מהסשן: {e}")
        return render(request, "main/error.html", {"message": "⚠️ שגיאה בטעינת הנתונים, נסה שוב."})

from io import BytesIO
from django.http import HttpResponse
import pandas as pd

from django.http import HttpResponse
import pandas as pd

def download_excel_view(request, cluster_id):
    print("✅ download_excel_view was called")
    print("🔎 Cluster ID:", cluster_id)

    data_json = request.session.get('order_filtered')
    print("🧪 יש order_filtered?", bool(data_json))

    data_types = request.session.get('data_types_order_filtered')
    print("🧪 יש data_types?", bool(data_types))

    if not data_json:
        return HttpResponse("אין נתונים להורדה", status=400)

    try:
        df = pd.read_json(data_json)
    except Exception as e:
        print("❌ שגיאה ב־read_json:", e)
        return HttpResponse("שגיאה בטעינת הנתונים", status=500)

    try:
        for col, dtype_str in data_types.items():
            df[col] = df[col].astype(dtype_str)
    except Exception as e:
        print("❌ שגיאה בהמרת טיפוס:", e)

    try:
        df_cluster = df[df['Cluster'] == int(cluster_id)].copy()
        df_cluster.insert(0, "מספר תחנה", range(1, len(df_cluster) + 1))
    except Exception as e:
        print("❌ שגיאה בעיבוד הקלאסטר:", e)
        return HttpResponse("שגיאה בעיבוד קובץ", status=500)

    try:
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_cluster.to_excel(writer, index=False)

        output.seek(0)
        response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename=cluster_{cluster_id}_orders.xlsx'
        return response
    except Exception as e:
        print("❌ שגיאה ביצירת הקובץ:", e)
        return HttpResponse("שגיאה ביצירת קובץ אקסל", status=500)
