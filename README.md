# AI Web Scraper

An intelligent web scraping tool powered by AI that can automatically extract structured data from any website. Supports both JavaScript-rendered and static content through Playwright and BeautifulSoup4.

![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## 🌟 Features

- 🤖 AI-powered data extraction
- 🌐 Support for JavaScript-rendered websites
- 🚀 Built-in CLI interface
- 💾 Save generated scraping code
- 🔄 Automatic handling of dynamic content
- 🛡️ Anti-detection mechanisms
- 📦 Caching support
- 🎯 Custom data extraction prompts

# 🚀 Quick Start

## Prerequisites
### Clone the repository

```shell
git clone https://github.com/NotoriousBigg/ai-web-scraper.git
cd ai-web-scraper
```

### Create and activate virtual environment (optional but recommended)
```shell
python -m venv venv source venv/bin/activate # Linux/Mac
```
### or
```
.\venv\Scripts\activate # Windows
```

### Install required packages
```shell
pip install -r requirements.txt
```

### Install Playwright browsers
```shell
playwright install chromium
```

# Configuration

1. Create a `.env` file in the project root:
```text
REDIS_URI="YOUR-REDIS-URI"
GEMINI_API_KEY="YOUR-GEMINI-API-KEY"
```

### Usage
```shell
$ python3 main.py
```


## 🗺️ Roadmap

- [ ] Automated testing suite
- [ ] RESTful API integration
- [ ] Web interface
- [ ] Telegram Bot integration
- [ ] Selenium support as alternative to Playwright

## 🛠️ Technical Details

### Components

- **AI Engine**: Powered by Gemini AI for intelligent data extraction
- **Web Scraping**: 
  - Playwright for JavaScript-rendered content
  - BeautifulSoup4 for static content
- **CLI Interface**: Interactive command-line interface
- **Caching System**: Reduces redundant requests

### Supported Features

- Dynamic content loading
- Custom waiting strategies
- Stealth mode
- Rate limiting
- Error handling
- Content verification


## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Playwright](https://playwright.dev/) for browser automation
- [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) for HTML parsing
- [Google](https://aistudio.google.com/) for Gemini AI integration

## 📧 Contact

NotoriousBigg - [Github](https://github.com/NotoriousBigg)

Project Link: [https://github.com/NotoriousBigg/ai-web-scraper](https://github.com/NotoriousBigg/ai-web-scraper)