from binance.client import Client
import datetime
import time
import requests
import json
import math
import os





"""
    Функция проверки попадания текущего времени в заданных в часах промежуток

    :param start_time: Начало временного периода 
    :type  start_time: int.
    :param   end_time: Начало временного периода
    :type    end_time: int.
    
    :returns: True или False
"""
def time_in_range(start_time, end_time):

    start   = datetime.time(start_time, 0, 0)
    end     = datetime.time(end_time, 0, 0)
    hours   = (int(time.strftime("%H", time.gmtime(time.time()))) + 3) % 24
    minutes = int(time.strftime("%M", time.gmtime(time.time())))
    x       = datetime.time(hours, minutes, 0)
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end


"""
    Функция отправки сообщения в телеграм 

    :param     text: Отправляемый текст сообщения
    :type      text: str.
    :param tg_token: Токен телеграм-бота из BotFather
    :type  tg_token: str.
    :param  user_id: ID пользователя бота
    :type   user_id: int.

"""
def send_msg(text, tg_token, user_id):
    url_req = (
        "https://api.telegram.org/bot"
        + tg_token
        + "/sendMessage"
        + "?chat_id="
        + str(user_id)
        + "&text="
        + text
    )
    requests.get(url_req)

"""
    Функция чтения json-файла

    :param     filename: Название файла
    :type      filename: str.
    
    :returns: dict или list
"""
def json_load(filename):
    with open(filename, "r", encoding="utf8") as read_file:
        result = json.load(read_file)
    return result

"""
    Функция записи в json-файл

    :param     filename: Название файла
    :type      filename: str.
    :param     data: Записываемые данные
    :type      data: list or dict.
  
"""
def json_dump(filename, data):
    with open(filename, "w", encoding="utf8") as write_file:
        json.dump(data, write_file, ensure_ascii=False)



# Куки для авторизации на Binance (время жизизни 5 дней)
try:
    cookies        = json_load(r"./json/cookies.json")
    headers        = json_load(r"./json/headers.json")
except:
    print('Заполните корректно файл с куки и заголовками')
    
try:
    config         = json_load(r"./json/config.json")
except:
    print('Заполните корректно файл с настройками')

token          = config['tg_token']
user_id        = config['user_id']
api_key        = config['api_key']
api_secret     = config['api_secret']
sl             = config['day_stop_loss']
start_time     = config['balance_update_time_start']
end_time       = config['balance_update_time_end']

# Словарь со сведениями об открытых позициях 
entry_prices   = {}
client         = Client(api_key=api_key, api_secret=api_secret)

# Блок првоерки наличия сведений о последней записи дневного баланса
try:
    day_start_balance = json_load(r"./json/balance.json")[0]
except:
    day_start_balance = float(client.futures_account_balance()[5]["balance"])
    json_dump("./json/balance.json", [day_start_balance])



update_flag = True

while True:

    try:
        balance = float(client.futures_account_balance()[5]["balance"])
        
        # Обновление дневного баланса в заданный промежуток времени
        if time_in_range(start_time, end_time) and update_flag:
            day_start_balance = balance
            update_flag       = False
            json_dump("./json/balance.json", [day_start_balance])
            send_msg("Дневной баланс обновлен", token, user_id)
            
        if not time_in_range(start_time, end_time):
            update_flag = True

        timestamp_cookies = os.stat("cookies.json").st_mtime

        # Проверка акутальности куки с учетом их времени жизни
        if (time.time() - timestamp_cookies) / 86400 > 4:
            current_orders = client.futures_position_information()
            for position in current_orders:
                
                #  если куки протухли, то открытые позиции будут автоматически закрываться
                if float(position["positionAmt"]) != 0:
                    send_msg("Без обновления куки торговля невозможна", token, user_id)
                    entry_prices[position["symbol"]] = {}
                    entry_prices[position["symbol"]]["price"] = float(
                        position["entryPrice"]
                    )
                    entry_prices[position["symbol"]]["positionAmt"] = float(
                        position["positionAmt"]
                    )
                    entry_prices[position["symbol"]]["USDT"] = abs(
                        float(position["notional"])
                    )
                    entry_prices[position["symbol"]]["PNL"] = float(
                        position["unRealizedProfit"]
                    )
                    entry_prices[position["symbol"]]["close_type"] = (
                        "BUY" if float(position["positionAmt"]) < 0 else "SELL"
                    )

                    client.futures_create_order(
                        symbol=position["symbol"],
                        side=entry_prices[position["symbol"]]["close_type"],
                        type="MARKET",
                        quantity=abs(entry_prices[position["symbol"]]["positionAmt"]),
                    )
                    entry_prices.pop(position["symbol"])
            
        #  если прeвышен дневной стоп-лосс, то открытые позиции закрываются и торговля на бирже блокируется на сутки
        if (100 - balance / day_start_balance * 100) > sl:
            current_orders = client.futures_position_information()
            
            # закрытие позиций
            for position in current_orders:

                if float(position["positionAmt"]) != 0:
                    entry_prices[position["symbol"]] = {}
                    entry_prices[position["symbol"]]["price"] = float(
                        position["entryPrice"]
                    )
                    entry_prices[position["symbol"]]["positionAmt"] = float(
                        position["positionAmt"]
                    )
                    entry_prices[position["symbol"]]["USDT"] = abs(
                        float(position["notional"])
                    )
                    entry_prices[position["symbol"]]["PNL"] = float(
                        position["unRealizedProfit"]
                    )
                    entry_prices[position["symbol"]]["close_type"] = (
                        "BUY" if float(position["positionAmt"]) < 0 else "SELL"
                    )

                    coeff = 0
                    if entry_prices[position["symbol"]]["close_type"] == "BUY":
                        coeff = (
                            1
                            - float(position["markPrice"])
                            / float(entry_prices[position["symbol"]]["price"])
                        ) * 100

                    else:
                        coeff = (
                            1
                            - float(
                                entry_prices[position["symbol"]]["price"]
                                / float(position["markPrice"])
                            )
                        ) * 100

                    client.futures_create_order(
                        symbol=position["symbol"],
                        side=entry_prices[position["symbol"]]["close_type"],
                        type="MARKET",
                        quantity=abs(entry_prices[position["symbol"]]["positionAmt"]),
                    )
                    entry_prices.pop(position["symbol"])
                    send_msg(
                        "Закрыта позиция по {}, убыток {} USDT".format(
                            position["symbol"],
                            (coeff)
                            * float(position["positionAmt"])
                            * float(position["entryPrice"])
                            / 100,
                        ), 
                        token, 
                        user_id
                    )

                    
             
            # Блокировка торговли 
            start_day = (math.floor(time.time() / 86400) * 86400) * 1000
            end_day   = (math.floor(time.time())) * 1000 + (3600 * 1 * 1000)
            data      = (
                        "{inCoolingDuration:true,startTime:"
                        + str(start_day)
                        + ",endTime:"
                        + str(end_day)
                        + "}"
            )
            
            response = requests.post(
                "https://www.binance.com/bapi/futures/v1/private/future/responsible/save-responsible-config",
                cookies=cookies,
                headers=headers,
                data=data,
            )
            send_msg('Торговля ограничена: {}'.format(str(response.text)), token, user_id)

    except Exception as e:
        send_msg("Ошибка в дневном риск-менеджере: {}".format(str(e)), token, user_id)
