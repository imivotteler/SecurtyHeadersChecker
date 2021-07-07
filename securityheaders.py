import os
import sys
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from slack_sdk.webhook import WebhookClient

# TODO
# Add scores to a DB (Dynamo? Mongo?)
# Only alert if the score gets worse than it was last time the check ran
# Message owning team alerting channel


# obtain environment vars for Cloudflare credentials
global headers
try:
    headers = {
        'X-Auth-Email': os.environ['CF_EMAIL'],
        'X-Auth-Key': os.environ['CF_KEY'],
        'Content-Type': 'application/json',
    }
except KeyError:
    print("You need to set your Cloudflare auth environment vars first.\nNeeds: CF_EMAIL and CF_KEY.\nEdit and run setup.sh")
    sys.exit()


# obtain environment vars for Slack Webhook
try:
    slack_webhook = os.environ['CF_WEBHOOK']
        
except KeyError:
    print("You need to set your Slack Webhook URL\nNeeds: CF_WEBHOOK.\nEdit and run setup.sh")
    sys.exit()


def log_results(report_data, current_domain):
    '''
    Write the results of the check to a file.
    TODO: replace with writing to a DB
    '''
    dateTimeObj = datetime.now()
    logfile_timestamp = (str(dateTimeObj.year) + '_' + str(dateTimeObj.month) + '_' + str(dateTimeObj.day))

    # write formatted data
    f = open(logfile_timestamp + ".log", "a")
    f.write(current_domain + ", " + report_data + '\n')
    f.close()


def good_score_check(score_input):
    '''
    Check if a site has a good score in which case we can ignore it
    '''
    matches = ["A", "B", "scoring problem"]
    if any(x in str(score_input) for x in matches):
        print("This site has a good or undeterminable score. Ignoring.")
        return True
    else:
        print("This site has a bad score. Posting!")
        return False


def post_to_slack_bulk(report):
    '''
    Post a list of sites and their scores to our Slack alerting channel
    '''
    url = slack_webhook # set the slack webhook from the environment 
    
    webhook = WebhookClient(url)
    response = webhook.send(
        text="fallback",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": report
                }
            }
        ]
    )


def check_securityheaders(scan_url):
    '''
    Call securityheaders.com and scrape the result of the supplied URL
    '''
    URL = 'https://securityheaders.com/?q=' + scan_url + '&followRedirects=on'
    page = requests.get(URL)

    soup = BeautifulSoup(page.content, 'html.parser')

    try:
        scraped_score = soup.find_all("div", {"class": lambda L: L and L.startswith('score_')})

        score_value = (str(scraped_score).split("<span>")[1].split("</span>")[0])
        print(score_value)
        return score_value

    except Exception as e:
        print (e)
        return "scoring problem"


# initial request to get total pages
response = requests.get('https://api.cloudflare.com/client/v4/zones', headers=headers)
domainList = json.loads(response.content)
domainListPages = (domainList["result_info"]["total_pages"])


def main():
    '''
    Perform the main function of the script
    '''
    main_report_text = []
    main_report_string = ""
    currentPage = 1
    # loop through all pages of results
    while currentPage <= domainListPages:
        params = (
        ('status', 'active'),
        ('page', currentPage),
        ('per_page', '20'),
        ('order', 'status'),
        ('direction', 'desc'),
        ('match', 'all'),
        )
        domainListResponse = requests.get('https://api.cloudflare.com/client/v4/zones', headers=headers, params=params)
        currentPage += 1
        domainListResults = json.loads(domainListResponse.content)

        for domain in domainListResults["result"]:
            print("Checking " + domain["name"])
            # try HTTPS first, if that doesn't work try HTTP
            try:
                currentURL = "https://" + domain["name"]
            except:
                currentURL = "http://" + domain["name"]
                print("HTTPS inaccessible. Reverting to HTTP.")

            sec_report = check_securityheaders(currentURL)
            log_results(str(sec_report), domain["name"])

            if not good_score_check(str(sec_report)):
                # if the site scores badly, log it. otherwise ignore it.
                main_report_string = main_report_string + (domain["name"] + " Score: " + str(sec_report) + " <https://securityheaders.com/?q=" + domain["name"] + "&followRedirects=on|More Info>\n")

        post_to_slack_bulk(str(main_report_string))
        main_report_string = ""


#run the main function that does everything
main()
