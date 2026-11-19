// Trimmed /api/weather/predict responses, in the shape the backend returns.

const park = {
  park_code: "zion",
  park_name: "Zion National Park",
  state: "UT",
  latitude: 37.2,
  longitude: -112.99,
  weather_location_note: "Weather point: Zion Canyon Visitor Center (NPS visitor center).",
};

const suitability = {
  score: 93.6,
  label: "Excellent",
  components: { temperature: 100, precipitation: 81.6, wind: 100, snow: 100 },
  weights: { temperature: 0.4, precipitation: 0.35, wind: 0.15, snow: 0.1 },
  notes: [],
};

export const climatePrediction = {
  park,
  travel_date: "2027-04-15",
  days_ahead: 165,
  activity: "hiking",
  prediction_type: "climate_estimate",
  model_name: "seasonal_regression",
  source: "ParkWise climate model: Seasonal regression with trend (Open-Meteo history 2015–2025)",
  units: { temperature: "celsius", precipitation: "mm", wind_speed: "km/h" },
  temperature: {
    max_c: 19.6,
    min_c: 4.3,
    max_range_c: [13.7, 25.8],
    min_range_c: [0.4, 8.9],
    range_note: "80% range, set from this model's past errors at this park in this month.",
  },
  precipitation: { probability: 0.184, kind: "climate_model_probability", wet_day_threshold_mm: 1.0, expected_mm: null },
  snow: { probability: 0.0 },
  wind: { max_kmh: 19.6 },
  suitability,
  summary: "…",
  uncertainty: "This is not a forecast.",
  notes: [],
  generated_at: "2026-11-01T20:00:00+00:00",
};

export const forecastPrediction = {
  ...climatePrediction,
  travel_date: "2026-11-05",
  days_ahead: 4,
  prediction_type: "forecast",
  model_name: "open_meteo_forecast",
  source: "Open-Meteo Forecast API",
  precipitation: { probability: 0.4, kind: "forecast_probability", wet_day_threshold_mm: 1.0, expected_mm: 5.1 },
  suitability: { ...suitability, score: 52, label: "Fair", notes: ["Snow is likely."] },
  notes: ["Snow is likely."],
  snow: { probability: 0.4 },
  uncertainty: "Forecasts are most reliable for the next few days.",
};
