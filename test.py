import requests
from bs4 import BeautifulSoup
import re




def extract_torrent_data(html_content):
    """
    Extracts torrent data (title, quality, magnet link, date, size) from the given HTML.

    Args:
        html_content: The HTML content of the webpage.

    Returns:
        A list of dictionaries, where each dictionary contains the extracted data for a single torrent.  Returns an empty list if no data is found.

    """
    soup = BeautifulSoup(html_content, 'xml')  # Use xml parser for RSS feeds
    items = soup.find_all('item')
    torrent_data = []

    for item in items:
        title = item.find('title').text.strip()
        magnet_link = item.find('link').text.strip() if item.find('link') else None #handle potential missing magnet link
        date_str = item.find('pubDate').text.strip()
        size_str = item.find('subsplease:size').text.strip()
        category = item.find('category').text.strip()


        # Extract quality (assuming it's part of the title or category)
        quality_match = re.search(r'(\d+p)', title) or re.search(r'(\d+p)', category)
        quality = quality_match.group(1) if quality_match else None


        #Clean up size string and convert to float
        size_match = re.search(r'([\d.]+)\s*MiB', size_str)
        size = float(size_match.group(1)) if size_match else None #handle potential error in size extraction


        torrent_data.append({
            'title': title,
            'quality': quality,
            'magnet_link': magnet_link,
            'date': date_str,
            'size': size,

        })
    return torrent_data

res = requests.get("https://subsplease.org/rss/?r=720")
html_content = res.content
# Extract data
torrent_info = extract_torrent_data(html_content)

# Print or save the extracted data
if torrent_info:
    for torrent in torrent_info:
        print("Title:", torrent['title'])
        print("Quality:", torrent['quality'])
        print("Magnet Link:", torrent['magnet_link'])
        print("Date:", torrent['date'])
        print("Size:", torrent['size'], "MiB")
        print("-" * 20)  # Separator between torrents

else:
    print("No torrent data found in the provided HTML.")