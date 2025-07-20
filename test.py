#Import necessary libraries
from bs4 import BeautifulSoup
import requests
import pandas as pd

#Specify the URL
url = "https://tv.kresswell.me"

#Fetch the webpage
response = requests.get(url)
response.raise_for_status() # Raise an exception for bad status codes

#Parse the HTML content
soup = BeautifulSoup(response.content, "html.parser")


#Find the TV section
tv_section = soup.find("div", class_="channels-wrapper")

#Extract TV data
tv_data = {
    "title": tv_section.find("h3").text.strip(),
    "description": tv_section.find("p").text.strip(),
    "link": tv_section.find("a")["href"].strip(),
}


#Create a Pandas DataFrame
df = pd.DataFrame([tv_data])

#Display the DataFrame in the terminal as a table
print(df.to_string(index=False))
