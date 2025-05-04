# # import sys
# # import requests
# # from bs4 import BeautifulSoup, SoupStrainer

# # home_url = 'https://parivahan.gov.in/rcdlstatus/'
# # post_url = 'https://parivahan.gov.in/rcdlstatus/vahan/rcDlHome.xhtml'
# # # Everything before the last four digits: MH02CL
# # first = sys.argv[1]
# # # The last four digits: 0555
# # second = sys.argv[2]

# # r = requests.get(url=home_url)
# # cookies = r.cookies
# # soup = BeautifulSoup(r.text, 'html.parser')
# # print(soup)
# # viewstate = soup.select('input[name="javax.faces.ViewState"]')[0]['value']

# # data = {
# #     'javax.faces.partial.ajax':'true',
# #     'javax.faces.source': 'form_rcdl:j_idt32',
# #     'javax.faces.partial.execute':'@all',
# #     'javax.faces.partial.render': 'form_rcdl:pnl_show form_rcdl:pg_show form_rcdl:rcdl_pnl',
# #     'form_rcdl:j_idt32':'form_rcdl:j_idt32',
# #     'form_rcdl':'form_rcdl',
# #     'form_rcdl:tf_reg_no1': first,
# #     'form_rcdl:tf_reg_no2': second,
# #     'javax.faces.ViewState': viewstate,
# # }

# # r = requests.post(url=post_url, data=data, cookies=cookies)
# # soup = BeautifulSoup(r.text, 'html.parser')
# # table = SoupStrainer('tr')
# # soup = BeautifulSoup(soup.get_text(), 'html.parser', parse_only=table)
# # print(soup.get_text())

# # import http.client

# # conn = http.client.HTTPSConnection("rto-vehicle-details.p.rapidapi.com")

# # payload = "{"vehicle_number":"GJ03ER0563"}"

# # headers = {
# #     'x-rapidapi-host': "rto-vehicle-details.p.rapidapi.com",
# #     'Content-Type': "application/json"
# # }

# # conn.request("POST", "/api3", payload, headers)

# # res = conn.getresponse()
# # data = res.read()

# # print(data.decode("utf-8"))

# import requests

# url = "https://rto-vehicle-details.p.rapidapi.com/api3"

# payload = { "vehicle_number": "MH02FB2727" }
# headers = {
# 	"x-rapidapi-host": "rto-vehicle-details.p.rapidapi.com",
# 	"Content-Type": "application/json"
# }

# response = requests.post(url, json=payload, headers=headers)

# print(response.json())
# jibs-opaque-88
# UP32HQ0999
import requests
import xml.etree.ElementTree as ET
import json

# API request setup
url = "https://www.carregistrationapi.in/api/reg.asmx/CheckIndia"
payload = {
    "RegistrationNumber": "UP32HQ0999",
    "username": "jibs-opaque-88"
}
headers = {
    "Content-Type": "application/x-www-form-urlencoded"
}

# Send POST request
response = requests.post(url, data=payload, headers=headers)

# Parse XML from response
root = ET.fromstring(response.text)

# Extract vehicleJson (namespace-aware)
ns = {'ns': 'http://regcheck.org.uk'}
vehicle_json_text = root.find('ns:vehicleJson', ns).text

# Parse the JSON string
vehicle_data = json.loads(vehicle_json_text)

# Extract key details
model = vehicle_data.get("CarModel", {}).get("CurrentTextValue", "")
owner = vehicle_data.get("Owner", "")
location = vehicle_data.get("Location", "")
variant = vehicle_data.get("Variant", "")
fuel_type = vehicle_data.get("FuelType", {}).get("CurrentTextValue", "")
registration_date = vehicle_data.get("RegistrationDate", "")
insurance_expiry = vehicle_data.get("Insurance", "")
image_url = vehicle_data.get("ImageUrl", "")

# Print extracted details
print(f"Model: {model}")
print(f"Variant: {variant}")
print(f"Owner: {owner}")
print(f"Location: {location}")
print(f"Fuel Type: {fuel_type}")
print(f"Registration Date: {registration_date}")
print(f"Insurance Expiry: {insurance_expiry}")
print(f"Vehicle Image URL: {image_url}")
