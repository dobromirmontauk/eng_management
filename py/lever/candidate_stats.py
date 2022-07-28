import json
import requests
from requests.auth import HTTPBasicAuth
from types import SimpleNamespace


def get_opportunities():
    opportunities_url = 'https://api.lever.co/v1/opportunities'
    has_next = True
    opportunities = []
    page = 1
    offset = ''
    while has_next:
        print(f'Fetching page {page}')
        response = run_request(opportunities_url, offset=offset)
        new_opportunities = Opportunity.from_json(response)
        opportunities.extend(new_opportunities)
        if response.hasNext:
            if response['next'] == offset:
                raise Exception("Whoops! We fetched the same page as last time!")
            offset = response['next']
            page += 1
        else:
            has_next = False
    return opportunities


def run_request(url, offset=''):
    if offset:
        url = url + f'?offset={offset}'
    response = requests.get(url,
                            auth=HTTPBasicAuth(username='XuS0Vgo2ZmoZJSfIQOcVxyVrb4WuiUmJVWxl9k+69M3wSF7X',
                                               password=''))
    if response.ok:
        return json.loads(response.content)
    else:
        raise Exception(response.raise_for_status())


class Opportunity(SimpleNamespace):

    @classmethod
    def from_json(cls, json):
        opportunities = []
        for element in json['data']:
            opportunity = Opportunity(**element)
            opportunity.get_interviews()
            opportunities.append(opportunity)
        return opportunities

    def get_interviews(self):
        interviews_url = f'https://api.lever.co/v1/opportunities/{self.id}/interviews'
        has_next = True
        interviews = []
        page = 1
        offset = ''
        while has_next:
            print(f'Fetching page {page}')
            response = run_request(interviews_url, offset=offset)
            new_interview = Interview.from_json(response)
            interviews.extend(new_interview)
            if response.hasNext:
                if response['next'] == offset:
                    raise Exception("Whoops! We fetched the same page as last time!")
                offset = response['next']
                page += 1
            else:
                has_next = False


class Interview(SimpleNamespace):

    @classmethod
    def from_json(cls, json):
        interviews = []
        for element in json['data']:
            interview = Interview(**element)
            interviews.append(interview)
        return interviews


if __name__ == "__main__":
    ops = get_opportunities()
    print(ops)
