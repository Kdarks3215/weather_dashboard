import os
import json
import boto3
import requests
from datetime import datetime, timedelta
from dash import Dash, html, dcc
from dash.dependencies import Input, Output, State
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class WeatherDashboard:
    def __init__(self):
        self.api_key = os.getenv('OPENWEATHER_API_KEY')
        self.bucket_name = os.getenv('AWS_BUCKET_NAME')
        self.s3_client = boto3.client('s3')
        self.last_api_call_time = {}  # To track the last API call time for each city

    def create_bucket_if_not_exists(self):
        """Create S3 bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            print(f"Bucket {self.bucket_name} exists.")
        except:
            print(f"Creating bucket {self.bucket_name}...")
            self.s3_client.create_bucket(Bucket=self.bucket_name)
            print(f"Bucket {self.bucket_name} created successfully.")

    def fetch_weather(self, city):
        """Fetch weather data from OpenWeather API"""
        base_url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": self.api_key,
            "units": "metric"
        }
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            self.last_api_call_time[city] = datetime.now()  # Update last API call time
            return response.json()
        except requests.exceptions.RequestException as e:
            log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{log_time}] Error fetching weather data for {city}: {e}")
            return None

    def save_weather_to_s3(self, city, weather_data):
        """Save weather data to S3 bucket"""
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        file_name = f"weather-data/{city}-{timestamp}.json"
        try:
            weather_data['timestamp'] = timestamp
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_name,
                Body=json.dumps(weather_data),
                ContentType='application/json'
            )
            log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{log_time}] Weather data for {city} saved to S3.")
        except Exception as e:
            log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{log_time}] Error saving weather data for {city} to S3: {e}")

    def get_latest_weather_from_s3(self, city):
        """Retrieve the latest weather data for a city from S3"""
        prefix = f"weather-data/{city}-"
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            if 'Contents' not in response:
                print(f"No weather data found for {city} in S3.")
                return None

            latest_file = max(response['Contents'], key=lambda obj: obj['LastModified'])
            file_obj = self.s3_client.get_object(Bucket=self.bucket_name, Key=latest_file['Key'])
            weather_data = json.loads(file_obj['Body'].read().decode('utf-8'))
            return weather_data
        except Exception as e:
            log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{log_time}] Error retrieving weather data for {city} from S3: {e}")
            return None

# Initialize Dash app with Font Awesome stylesheet
external_stylesheets = ["https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"]
app = Dash(__name__, external_stylesheets=external_stylesheets)
dashboard = WeatherDashboard()
popular_cities = ["Accra", "Kumasi", "Tamale", "Takoradi", "Cape Coast"]

# Create S3 bucket if it doesn't exist
dashboard.create_bucket_if_not_exists()

# Query API and save data to S3
def query_and_save_weather():
    for city in popular_cities:
        weather_data = dashboard.fetch_weather(city)
        if weather_data:
            dashboard.save_weather_to_s3(city, weather_data)

query_and_save_weather()  # Initial query and save
app.layout = html.Div(
    style={'textAlign': 'center', 'fontFamily': 'Arial, sans-serif', 'padding': '20px'},
    children=[
        html.H1("Weather Dashboard", style={'marginBottom': '20px', 'color': '#111827'}),
        html.Div(
            style={'display': 'flex', 'justifyContent': 'center', 'alignItems': 'center', 'marginBottom': '20px'},
            children=[
                html.Div(id="last-updated-time", style={'marginRight': '10px', 'color': '#6b7280'}),
                html.Button(
                    html.I(className="fas fa-sync-alt", style={'fontSize': '18px', 'color': '#4CAF50'}),
                    id="refresh-button",
                    style={
                        'background': 'none',
                        'border': 'none',
                        'padding': '10px',
                        'cursor': 'pointer'
                    }
                )
            ]
        ),
        dcc.Dropdown(
            id='city-dropdown',
            options=[{"label": city, "value": city} for city in popular_cities],
            placeholder="Select a city",
            style={'marginBottom': '20px', 'width': '50%', 'margin': '0 auto'}
        ),
        html.Div(id="weather-data"),
        dcc.Interval(
            id='update-interval',
            interval=3600 * 1000,  # 1 hour in milliseconds
            n_intervals=0
        )
    ]
)

@app.callback(
    Output('weather-data', 'children'),
    [Input('city-dropdown', 'value')],
    [State('refresh-button', 'n_clicks')]
)
def update_weather_data(selected_city, n_clicks):
    if not selected_city:
        return html.P("Please select a city to view the weather.", style={'color': '#6b7280'})

    # Check the last API call time
    last_call = dashboard.last_api_call_time.get(selected_city)
    now = datetime.now()

    if last_call and (now - last_call) < timedelta(minutes=10):
        print(f"Skipping API call for {selected_city}. Last call was at {last_call}.")
    else:
        weather_data = dashboard.fetch_weather(selected_city)
        if weather_data:
            dashboard.save_weather_to_s3(selected_city, weather_data)

    weather_data = dashboard.get_latest_weather_from_s3(selected_city)
    if not weather_data:
        return html.P("No weather data available. Please try again later.", style={'color': '#ef4444'})

    return html.Div(
        style={
            'padding': '10px',
            'border': '1px solid #e5e7eb',
            'borderRadius': '8px',
            'backgroundColor': '#f9fafb'
        },
        children=[
            html.H4(f"City: {selected_city}", style={'color': '#1f2937', 'fontWeight': 'bold'}),
            html.P(f"Temperature: {round(weather_data['main']['temp'])}°C", style={'color': '#1f2937'}),
            html.P(f"Feels like: {round(weather_data['main']['feels_like'])}°C", style={'color': '#1f2937'}),
            html.P(f"Humidity: {weather_data['main']['humidity']}%", style={'color': '#1f2937'}),
            html.P(f"Conditions: {weather_data['weather'][0]['description'].capitalize()}", style={'color': '#1f2937'})
        ]
    )

@app.callback(
    Output('last-updated-time', 'children'),
    [Input('update-interval', 'n_intervals'), Input('refresh-button', 'n_clicks')]
)
def update_last_updated_time(n_intervals, n_clicks):
    current_time = datetime.now().strftime("%H:%M")
    return f"Last updated: {current_time}"

if __name__ == "__main__":
    app.run_server(debug=True,  host='0.0.0.0', port=80)
