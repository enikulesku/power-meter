#! /usr/bin/python

import json
import time
import datetime
import calendar

def split_months(data):
    sorted_data = sorted(data, key=lambda item: item["time"])

    months = []

    current_month = []
    for item in sorted_data:
        current_month.append(item)
        if item["type"] == "reset":
            months.append(current_month)
            current_month = [item, ]

    if len(current_month) > 0:
        months.append(current_month)

    return months


def calculate(months, tariffs):
    items = []
    day = 0
    night = 0
    night_off = 0
    for month in months:
        month_items = []
        month_day = 0
        month_night = 0
        previous_item = None
        for item in month:
            if previous_item:
                power_range = {"rawStart": previous_item, "rawEnd": item,
                               "startTime": parse_time(previous_item["time"]), "endTime": parse_time(item["time"]),
                               "day": item["day"] - previous_item["day"],
                               "night": item["night"] - previous_item["night"],
                               "type": previous_item["type"]}

                if previous_item["type"] == "heat":
                    power_range["mode"] = previous_item["mode"]
                    power_range["temp"] = previous_item["temp"]

                power_range["totalKw"] = power_range["day"] + power_range["night"]

                month_items.append(power_range)

                month_day += power_range["day"]
                month_night += power_range["night"]

            previous_item = item

        if len(month_items) == 0:
            continue

        day += month_day
        night += month_night

        month_total = {"day": month_day, "night": month_night, "totalKw": month_day + month_night, "items": month_items}
        apply_tariff(month_total, tariffs)

        night_price_without_discount = calculate_cost(month_night, tariffs, month_total["tariff"], False, month_total["limitExceeded"])
        night_off_month = night_price_without_discount - night_price_without_discount * tariffs["nightPercent"] / 100.0

        month_total["night_price_without_discount"] = night_price_without_discount
        month_total["night_off"] = night_off_month

        night_off += night_off_month

        items.append(month_total)

    return {"day": day, "night": night, "night_off": night_off, "items": items}


def apply_tariff(month_total, tariffs):
    sorted_tariffs = sorted(tariffs["tariffs"], key=lambda item: item["exp"])

    start_time = month_total["items"][0]["startTime"]
    current_tariff = None

    for current_tariff in sorted_tariffs:
        exp_date = parse_tariff_time(current_tariff["exp"])
        if exp_date > start_time:
            break

    current_price = None

    for price in sorted(current_tariff["pricing"], key=lambda item: item["start"] if "start" in item else None):
        if "start" not in price:
            current_price = price
            continue

        start = parse_tariff_date(price["start"])
        end = parse_tariff_date(price["end"])

        #ToDo: review
        if (start.tm_yday < end.tm_yday and start.tm_yday <= start_time.tm_yday < end.tm_yday) or\
                (start.tm_yday >= end.tm_yday and (start.tm_yday < start_time.tm_yday or end.tm_yday > start_time.tm_yday)):
            current_price = price


    total_kw = month_total["totalKw"]

    limit_exceeded = total_kw > current_price["limit"]
    month_total["limitExceeded"] = limit_exceeded

    day_cost = calculate_cost(month_total["day"], tariffs, current_price, False, limit_exceeded)
    month_total["dayCost"] = day_cost

    night_cost = calculate_cost(month_total["night"], tariffs, current_price, True, limit_exceeded)
    month_total["nightCost"] = night_cost

    month_total["tariff"] = current_price


def calculate_cost(value, tariffs, price, is_night, limit_exceeded):
    multiplier = (price["overLimitCost"] if limit_exceeded else price["cost"]) / 1000.0

    return value * multiplier if not is_night else value * multiplier * tariffs["nightPercent"] / 100.0


def parse_time(time_str):
    return time.strptime(time_str, "%y-%m-%d %H:%M")


def parse_tariff_time(time_str):
    return time.strptime(time_str, "%y-%m-%d")


def parse_tariff_date(time_str):
    return time.strptime(time_str, "%m-%d")

def get_hours(start_item, end_item):
    return (time.mktime(end_item["endTime"]) - time.mktime(start_item["startTime"])) / 60 / 60


def calculateAll(printAll = True):
    data = json.load(open('data.json'))

    months = split_months(data)

    tariffs = json.load(open('tariffs.json'))

    total = calculate(months, tariffs)

    config = json.load(open('config.json'))

    month = total["items"][-1]

    month_hours = get_hours(month["items"][0], month["items"][-1])
    total_kw = month["totalKw"]
    night = month["night"]
    cost = month["dayCost"] + month["nightCost"]

    night_price_without_discount = calculate_cost(night, tariffs, month["tariff"], False, month["limitExceeded"])
    night_off = night_price_without_discount - night_price_without_discount * tariffs["nightPercent"] / 100.0

    avg_load = (total_kw / month_hours)

    last_power_range = month["items"][-1]
    last_hours = get_hours(last_power_range, last_power_range)
    avg_load_last = (last_power_range["totalKw"] / last_hours)

    last_time = datetime.datetime.fromtimestamp(time.mktime(month["items"][-1]["endTime"]))
    last_month_day = datetime.datetime(last_time.year, last_time.month, calendar.monthrange(last_time.year, last_time.month)[1], 0, 0)

    hours_to_end = (last_month_day - last_time).total_seconds() / 60 / 60

    limit = month["tariff"]["limit"]

    kw_expected = int(round(avg_load * hours_to_end, 0) + total_kw)

    if printAll:
        print("Total: {0} / {1} kW".format(total_kw, limit))
        print("====================")
        print("Avg: {0} kW/h".format(round(avg_load, 2)))
        print("Expected: {0} / {1} kW".format(kw_expected, limit))
        print("====================")
        print("Avg(last): {0} kW/h".format(round(avg_load_last, 2)))
        print("Expected(last): {0} / {1} kW".format(round(avg_load_last * hours_to_end) + total_kw, limit))
        print("====================")
        print("Cost: {0} grn".format(round(cost, 2)))
        print("====================")
        print("Night: {0}%".format(night * 100 / total_kw))
        print("Night off: {0} grn".format(round(month["night_off"], 2)))

        print("====================")
        print("Total Night off: {0} grn".format(round(total["night_off"], 2)))

    return total_kw, limit, kw_expected

calculateAll()
