"""
Business logic. API routes call these functions; they never touch HTTP details.

Keeping logic here (not in the route handlers) is what lets teammates import
`predict_weather()` directly in Python without running a web server.
"""
