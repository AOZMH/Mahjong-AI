import json
import random
import time
import pickle

# 全局开始时间
t0 = time.time()


def parse_input(full_input):

    # 解析读入的JSON
    if "data" in full_input:
        my_data = full_input["data"]; # 该对局中，上回合该Bot运行时存储的信息
    else:
        my_data = None

    # 分析自己收到的输入和自己过往的输出，并恢复状态
    my_cards = []   # card 列表
    avail_cards = []    # 当前可以打的牌列表, 排除吃碰杠之后的死牌
    last_card = None    # 上回合打出的牌
    all_requests = full_input["requests"]
    all_responses = full_input["responses"]
    for ix in range(len(all_requests)):     # 因为当前turn也可能新增牌(IX=2)，所以最后一轮也得算
        myInput = all_requests[ix].strip() # i回合我的输入
        #myOutput = all_responses[ix].strip() # i回合我的输出
        
        if ix == 0:     # 第一轮只需要记录自己的ID
            myID = int(myInput.split(' ')[1])
        elif ix == 1:   # 第二轮记录初始牌
            myInput = myInput.split(' ')[5:]    # 忽略花牌
            for cur_card in myInput:
                my_cards.append(cur_card)
                avail_cards.append(cur_card)
        else:   # 开始对局, 恢复局面
            myInput = myInput.split(' ')
            cur_index = int(myInput[0])
            if cur_index == 2:  # 自己摸到了一张牌
                my_cards.append(myInput[1])
                avail_cards.append(myInput[1])
            if cur_index == 3:  # draw/chi/peng/gang
                cur_id = int(myInput[1])
                if cur_id == myID:  # 自己做的动作，所以要更新牌型
                    if myInput[2] == 'PLAY':
                        my_cards.remove(myInput[3])
                        avail_cards.remove(myInput[3])
                    elif myInput[2] == 'PENG':
                        #assert(False)
                        my_cards.append(last_card)
                        # 碰的刻子之后不能打
                        avail_cards.remove(last_card)
                        avail_cards.remove(last_card)
                        my_cards.remove(myInput[3])
                        avail_cards.remove(myInput[3])
                    elif myInput[2] == 'CHI':
                        #assert(False)
                        my_cards.append(last_card)
                        avail_cards.append(last_card)
                        # 吃的那个顺子之后都不能打了
                        mid = myInput[3]
                        mid_num = int(mid[1])
                        avail_cards.remove(mid[0]+str(mid_num-1))
                        avail_cards.remove(mid)
                        avail_cards.remove(mid[0]+str(mid_num+1))
                        my_cards.remove(myInput[4])
                        avail_cards.remove(myInput[4])
                    elif myInput[2] == 'GANG':
                        #assert(False)
                        avail_cards.remove(last_card)
                        avail_cards.remove(last_card)
                        avail_cards.remove(last_card)
                    elif myInput[2] == 'BUGANG':
                        #assert(False)
                        pass
            last_card = myInput[-1]
    
    ret = {
        'turn_id': len(all_requests),
        'data': my_data,
        'id': myID,
        'cards': sorted(my_cards),
        'avail_cards': sorted(avail_cards),
        'cur_request': all_requests[-1].strip().split(' '),
    }
    return ret


def do_early_pass(dat):
    # 有些request只能pass，直接返回了就行
    myInput = dat['cur_request']
    cur_index = int(myInput[0])

    if cur_index == 2:
        # 摸到一张牌，需要做进一步决策，所以不pass
        return 'self_play'
    if cur_index == 3:
        # 别人打出一张牌，或者吃碰杠后打出一张牌，需要做进一步决策，也不pass
        cur_id = int(myInput[1])
        cur_action = myInput[2]
        if cur_id != dat['id'] and cur_action in ['PLAY', 'PENG', 'CHI']:
            return 'chi_peng_gang'
    
    # 否则都直接pass即可
    print(json.dumps({"response":"PASS", 'debug': [" ".join(dat['cards']), time.time()-t0]}))
    exit(0)


def load_precomputed_table(pkl_route):
    with open(pkl_route, 'rb') as fin:
        return pickle.load(fin)


def select_action(dat):
    # 加载计算好的评分表
    tables = load_precomputed_table(dat['pkl_route'])
    state = dat['state']
    debug = {
        'cards': " ".join(dat['cards']),
        'avail_cards': " ".join(dat['avail_cards']),
        'elapsed_time': time.time()-t0,
        'table_stats': list(map(len, tables)),
    }
    if state == 'self_play':
        
        # 出牌算法
        policy = 'table'
        play_card_selected = play_card(dat, tables, policy)
        print(json.dumps({"response":"PLAY {}".format(play_card_selected), 'debug': debug}))
    else:
        print(json.dumps({"response":"PASS", 'debug': debug}))
    exit(0)


def get_keys(cards):
    # 将card list转换成整数key，每种花色一个key
    # 如["B1", "B1", "B4"]对应的key为200100000
    tong_key, tiao_key, wan_key, feng_key, jian_key = 0,0,0,0,0
    for card in cards:
        if card[0] == 'B':
            tong_key += 10**(9-int(card[1]))
        elif card[0] == 'T':
            tiao_key += 10**(9-int(card[1]))
        elif card[0] == 'W':
            wan_key += 10**(9-int(card[1]))
        elif card[0] == 'F':
            feng_key += 10**(4-int(card[1]))    # F1~F4为东南西北
        elif card[0] == 'J':
            jian_key += 10**(3-int(card[1]))     # J1~J3为中发白
    return tong_key, tiao_key, wan_key, feng_key, jian_key


def cal_score(cards, tables):
    # 计算当前card list的胡牌概率/打分
    # 方法为: 将筒条万风箭分别拆出来，查表/搜索得到每种花色含/不含将的胡牌得分
    # 之后枚举，找到恰有一个将的所有牌胡牌概率最大值，作为cards的打分，总的分值用各花色分值求和而得
    # tables为tuple，包含三种花色牌胡牌概率表
    # TODO:
    #   1. 这个计算比较粗略，cards为包括了鸣牌了的所有牌，将枚举了可能的所在花色，但实际上是不一定可能的（比如风牌全部鸣了，就不能有将了），所以这个score是一个乐观估计
    #   2. 原始github实现计算了听牌，若cards已经听牌，则按照听牌数量计算打分，目前还没实现，之后实现

    all_keys = get_keys(cards)
    table_normal, table_feng, table_jian = tables
    all_tables = [table_normal, table_normal, table_normal, table_feng, table_jian]
    max_score, jiang_selected = -1, None

    # 枚举将在每一种花色的情况
    for jiang_type in range(5):
        is_jiang = [0]*5
        is_jiang[jiang_type] = 1
        cur_score = sum([cur_table[cur_key][cur_is_jiang] for cur_table, cur_key, cur_is_jiang in zip(all_tables, all_keys, is_jiang)])
        if cur_score > max_score:
            jiang_selected = jiang_type
            max_score = cur_score
    
    return max_score, jiang_selected


def play_card(dat, tables, policy='table'):
    # 出牌算法，策略可选为'random', 'table', 'search'
    # random为从可以打的牌中随机选一张
    # table为根据打表估值，枚举每一张可打牌，看哪一张去掉后总估值最大，选择该牌
    # search为搜索算法，待实现

    if policy == 'random':
        return random.choice(dat['avail_cards'])
    
    elif policy == 'table':
        max_score, play_card_selected = -1, None
        for card in set(dat['avail_cards']):
            dat['cards'].remove(card)
            cur_score, jiang_selected = cal_score(dat['cards'], tables)
            dat['cards'].append(card)
            print(card, cur_score)
            if cur_score > max_score:
                max_score = cur_score
                play_card_selected = card
        #print(play_card_selected)
        return play_card_selected

    else:
        raise NotImplementedError

def main():
    full_input = json.loads(input())
    ret = parse_input(full_input)
    state = do_early_pass(ret)
    ret['state'] = state
    ret['pkl_route'] = './data/Majiang/table_normal_feng_jian.pkl'
    select_action(ret)


if __name__ == "__main__":
    main()