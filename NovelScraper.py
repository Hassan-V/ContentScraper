import os
import re
import time
import dotenv
from colored import *
from typing import *
from fake_useragent import UserAgent
from ebooklib.epub import *
from bs4 import BeautifulSoup as soup
import unicodedata
import logging
import requests


class NovelScraper:
    """
    A class for scraping and creating EPUB files for novels.

    Attributes:
        REQUIRED_ENV_VARS (List[str]): A list of required environment variable names.
        LOG_FILENAME_TEMPLATE (str): The template for the log file name.
        LOG_LEVEL (int): The logging level.
        LOG_FORMAT (str): The log message format.
        LOG_DATEFMT (str): The log date format.
        EPUB_DIR (str): The directory for storing EPUB files.

    Methods:
        __init__(self, novel_name: str, batch_size: int = None) -> None:
            Initializes a NovelScraper instance.
        config_ebook_path(self, initial: int, end: int) -> None:
            Configures the output file path for the EPUB.
        get_int_input(self, prompt: str) -> int:
            Prompts the user for an integer input.
        get_novel_name(self) -> str:
            Prompts the user for the name of the novel.
        write_to_file(self, value: str) -> None:
            Writes a value to a file.
        get_url(self) -> str:
            Retrieves the URL for the next chapter to scrape.
        remove_pattern(self, data, match_string) -> str:
            Removes lines containing a specific pattern from a string.
        remove_exclusions(self, data, exclusions) -> str:
            Removes specified strings from a string.
        remove_last_p_tag(self, data) -> str:
            Removes the last <p> tag from an HTML string.
        clean_text(self, data) -> str:
            Cleans the text by removing unwanted patterns and tags.
        find_next_chapter_link(self, page_soup) -> str:
            Finds the URL of the next chapter in the given HTML soup.
        get_last_chapter_scraped(self) -> int:
            Retrieves the number of the last chapter that was scraped.
        scrape_one_webpage(self, web_url: str, webpage_no: int, retry_no: int = 1) -> Tuple[bool, str]:
            Scrapes a single webpage and returns the success status and the URL of the next chapter.
        get_choice(self, chapterNumber: int) -> str:
            Prompts the user for a choice (retry, skip, continue) when a chapter cannot be scraped.
        scrape_worker(self, batch_size: int) -> None:
            Scrapes multiple webpages in a batch.
        create_epub(self, author_name: str = 'Unknown', description: str = "A Novel") -> None:
            Creates an EPUB file for the scraped chapters.
    """
class NovelScraper:

    REQUIRED_ENV_VARS = ["BUTTON_ID", "DOMAIN_NAME",
                         "TEXT_CLASS", "URLS_FILE_NAME", "MAX_RETRY"]
    LOG_FILENAME_TEMPLATE = '{}.log'
    LOG_LEVEL = logging.INFO
    LOG_FORMAT = '%(asctime)s %(levelname)s: %(message)s'
    LOG_DATEFMT = '%Y-%m-%d %H:%M:%S'
    EPUB_DIR = "epub"

    def __init__(self: Self, novel_name: str, batch_size: int = None) -> None:
        dotenv.load_dotenv(override=True)

        for var in self.REQUIRED_ENV_VARS:
            if os.getenv(var) is None:
                raise Exception(
                    f"Missing required environment variable: {var}")

        self.novel_name = novel_name
        if novel_name is None:
            self.novel_name: str = self.get_novel_name()
        self.button_tag: str = os.getenv(self.REQUIRED_ENV_VARS[0])
        self.domain_name: str = os.getenv(self.REQUIRED_ENV_VARS[1])
        self.text_tag: str = os.getenv(self.REQUIRED_ENV_VARS[2])
        self.urls_file_name: str = os.getenv(self.REQUIRED_ENV_VARS[3])
        self.urls_file_path: str = os.path.join(
            self.EPUB_DIR, self.novel_name.replace(" ", "_"), "Links.txt")
        self.output_file_path: str = os.path.join(
            self.EPUB_DIR, self.novel_name.replace(" ", "_"))

        self.max_retries: int = int(os.getenv(self.REQUIRED_ENV_VARS[4]))

        self.epub_book: EpubBook = EpubBook()
        self.chapters: List[str] = []
        self.user_agent: UserAgent = UserAgent()
        self.start_time: time.time = time.time()
        self.initial_url: str = self.get_url()
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent.random})
        self.LOG_FILENAME = os.path.join(
            self.output_file_path, self.LOG_FILENAME_TEMPLATE.format(self.novel_name))

        logging.basicConfig(
            filename=self.LOG_FILENAME,
            level=self.LOG_LEVEL,
            format=self.LOG_FORMAT,
            datefmt=self.LOG_DATEFMT
        )

        self.batch_size: int = batch_size
        if batch_size is None:
            self.batch_size: int = self.get_int_input("Chapter Batch Size")

        os.makedirs(self.output_file_path, exist_ok=True)

    def config_ebook_path(self: Self, initial: int, end: int) -> None:
        self.output_file_path: str = os.path.join(
            self.output_file_path, f"{initial}-{end}")
        print(f"Output Path: {self.output_file_path}")

    def get_int_input(self: Self, prompt: str) -> int:

        while True:
            try:
                return int(input(f'{prompt}: '))
            except ValueError:
                pass

    def get_novel_name(self):
        return input("Enter the name of the novel: ").title()

    def write_to_file(self: Self, value: str) -> None:

        complete_path = self.urls_file_path

        if value == None:
            return

        try:
            with open(complete_path, 'r') as file:
                lines = file.readlines()
                if lines and lines[-1].strip() == str(value):
                    return
        except FileNotFoundError:
            directory = os.path.dirname(complete_path)
            os.makedirs(directory, exist_ok=True)

        with open(complete_path, 'a+') as file:
            file.write(str(value) + '\n')

    def get_url(self: Self):

        try:
            with open(self.urls_file_path, 'r') as file:
                lines = file.readlines()
                lines = [line.strip() for line in lines if line.strip()]
                if lines:
                    return lines[-1]
        except FileNotFoundError:
            chapter_url = input("Enter the First URL: ")
            self.write_to_file(value=chapter_url)
            return chapter_url

    # Cleaners

    def remove_pattern(self, data, match_string):
        return "\n".join(line for line in data.split("\n") if match_string.lower() not in line.lower())

    def remove_exclusions(self, data, exclusions):
        return re.sub('|'.join(map(re.escape, exclusions)), '', data)

    def remove_last_p_tag(self, data):
        data = soup(data, 'html.parser')
        p_tags = data.find_all('p')
        if p_tags:
            p_tags[-1].extract()
        return data

    def clean_text(self, data):
        data = unicodedata.normalize('NFKC', data)
        data = self.remove_pattern(data, "libread.com")
        data = self.remove_exclusions(data, [
            "Translator:",
            "Atlas Studios",
            "Editor:",
            "EndlessFantasy Translation"
        ])
        data = self.remove_last_p_tag(data)
        return str(data)

    '''____________________________________________________________'''

    def find_next_chapter_link(self: Self, page_soup):
        next_button = page_soup.find("a", {"id": self.button_tag})
        if next_button:
            next_link = next_button.get("href")
            if self.domain_name in next_link:
                return next_link
            else:
                return self.domain_name + next_link
        return None

    def get_last_chapter_scraped(self: Self):

        if not os.path.isdir(self.output_file_path):
            return None

        highest_value = None
        for folder_name in os.listdir(self.output_file_path):
            match = re.match(r"(\d+)-(\d+)", folder_name)
            if match:
                if os.path.isdir(os.path.join(self.output_file_path, folder_name)):
                    start, end = map(int, match.groups())

                    highest_value = end if highest_value is None else max(
                        highest_value, end)

        return highest_value

    def scrape_one_webpage(self: Self, web_url: str, webpage_no: int, retry_no: int = 1) -> str:

        if web_url is None:
            logging.info(f"No more chapters to scrape. Stopping at chapter {webpage_no}")
            return False, None

        while True:
            self.session.headers.update({'User-Agent': self.user_agent.random})

            try:
                req = self.session.get(web_url)
            except Exception as e:
                logging.error(f"Failed to get {web_url}: {e}")
                continue

            webpage_in_html: str = req.content
            req.close()
            parsed_html_webpage: str = soup(webpage_in_html, "html.parser")

            next_url = self.find_next_chapter_link(parsed_html_webpage)

            relevant_html_part: str = parsed_html_webpage.find(
                "div", {"class": self.text_tag})

            if retry_no > 8 % self.max_retries:
                logging.info(f'Retrying {web_url} for the {retry_no} time')

            if relevant_html_part:
                chapter: EpubHtml = EpubHtml(
                    title=f"Chapter {webpage_no}", file_name=f"chapter{webpage_no}.xhtml", lang='en')
                chapter.content = f'<h2>Chapter {webpage_no}</h2>{self.clean_text(relevant_html_part.prettify())}'
                self.epub_book.add_item(chapter)
                self.chapters.append(chapter)
                logging.info(
                    f'Successfully scraped chapter {webpage_no} from URL {web_url} on retry {retry_no}')
                return True, next_url

            if retry_no % self.max_retries == 0:
                user_choice = self.get_choice(chapterNumber=webpage_no)
                if user_choice.lower() == 'n':
                    chapter.content = f'<h2>Chapter {webpage_no}</h2> <p> Chapter not available </p>'
                    self.epub_book.add_item(chapter)
                    self.chapters.append(chapter)
                    logging.warning(
                        f'Unable to scrape chapter {webpage_no}. Continuing.')
                    return True, next_url
                elif user_choice.lower() == 'c':
                    web_url: str = input(
                        f'Enter the URL for chapter {webpage_no}: ')
                    logging.info(f'Attempting scrape for new URL: {web_url}')

            retry_no += 1

    def get_choice(self: Self,chapterNumber: int) -> str:
        while True:
            user_choice = input(
                f"Do you wish to keep retrying (c/y/n)\t\tChap{chapterNumber}: ")
            if user_choice.lower() in ("c", "y", "n"):
                return user_choice.lower()
            else:
                print("Hush, You wrong doer")

    def scrape_worker(self: Self, batch_size: int) -> None:
        current_url: str = self.initial_url
        last_valid_url: str = current_url
        if self.get_last_chapter_scraped() is not None:
            initial_chapter_number: int = self.get_last_chapter_scraped() + 1
        else:
            initial_chapter_number: int = 1
        for i in range(initial_chapter_number, initial_chapter_number + batch_size):
            has_more_pages, current_url = self.scrape_one_webpage(current_url, i)
            if current_url is not None:
                last_valid_url = current_url
            if not has_more_pages:
                break
        self.write_to_file(last_valid_url)
        self.config_ebook_path(initial_chapter_number, i)

    def create_epub(self: Self, author_name: str = 'Unknown', description: str = "A Novel") -> None:
        self.scrape_worker(self.batch_size)
        self.epub_book.set_title(self.novel_name)
        self.epub_book.set_language('en')
        self.epub_book.add_author(author_name)
        self.epub_book.add_metadata('DC', 'description', description)

        # Create the TOC
        self.epub_book.toc = [Section("Scraped Text")]
        for chapter in self.chapters:
            self.epub_book.toc.append(Link(chapter.file_name, chapter.title, chapter.id))

        self.epub_book.spine = ['nav'] + self.chapters
        self.epub_book.add_item(EpubNcx())
        self.epub_book.add_item(EpubNav())

        if not os.path.exists(self.output_file_path):
            os.makedirs(self.output_file_path)

        final_path: str = os.path.join(
            self.output_file_path, f"{self.novel_name} {self.batch_size}.epub")
        print(f"Final Path: {final_path}")
        write_epub(final_path, self.epub_book, {})