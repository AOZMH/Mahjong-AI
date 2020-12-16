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
                        avail_cards.remove(last_card)
                        avail_cards.remove(last_card)
                        avail_cards.remove(last_card)
                        avail_cards.remove(last_card)
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
        play_card_selected, max_score = play_card(dat, tables, policy)
        print(json.dumps({"response":"PLAY {}".format(play_card_selected), 'debug': debug}))
    else:
        cur_card = dat['cur_request'][-1]   # 上一张别人打出的牌
        policy, reward = 'table', 0
        global_max_score, global_action = -1, "PASS"  # 最终的选择

        # 尝试杠牌, 若可以则直接杠
        gang_res = gang_card_from_other(dat, tables, policy)
        if gang_res != False:
            max_score, action = gang_res
            if max_score > global_max_score:
                global_max_score = max_score
                global_action = action
        
        # 尝试碰牌
        peng_res = peng_card(dat, tables, policy, reward)
        if peng_res != False:
            max_score, action = peng_res
            if max_score > global_max_score:
                global_max_score = max_score
                global_action = action
        
        # 尝试吃牌
        chi_res = chi_card(dat, tables, policy)
        if chi_res != False:
            max_score, action, _ = chi_res
            if max_score > global_max_score:
                global_max_score = max_score
                global_action = action

        print(json.dumps({"response": global_action, 'debug': debug}))
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
    # NOTE:
    #   1. 这个计算仅针对没有鸣的牌(avail_cards)，计算活牌的估值
    # TODO:
    #   1. 原始github实现计算了听牌，若cards已经听牌，则按照听牌数量计算打分，目前还没实现，之后实现

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
        return random.choice(dat['avail_cards']), -1
    
    elif policy == 'table':
        max_score, play_card_selected = -1, None
        for card in set(dat['avail_cards']):
            dat['avail_cards'].remove(card)
            cur_score, jiang_selected = cal_score(dat['avail_cards'], tables)
            dat['avail_cards'].append(card)
            #print(card, cur_score)
            if cur_score > max_score:
                max_score = cur_score
                play_card_selected = card

        return play_card_selected, max_score

    else:
        raise NotImplementedError


def chi_card(dat, tables, policy='table'):
    # 吃牌算法，策略可选为 'table', 'search'
    # 若当前request不能吃，直接返回False，否则根据policy做决策
    # table根据打表估值，分别计算吃前/所有可能的吃后/吃后再出一张牌后avail_cards的估值
    
    cur_card = dat['cur_request'][-1]
    # 只有序数牌才能吃
    if cur_card[0] not in ('B', 'T', 'W'):
        return False
    # 只能吃上家
    if (int(dat['cur_request'][1])+1)%4 != dat['id']:
        return False
    
    if policy == 'table':
        avail_chi_actions = []  # 记录可行的吃法及相应估值结果
        raw_score, _ = cal_score(dat['avail_cards'], tables)
        max_score = raw_score
        card_l2 = cur_card[0]+str(int(cur_card[1])-2)
        card_l1 = cur_card[0]+str(int(cur_card[1])-1)
        card_r1 = cur_card[0]+str(int(cur_card[1])+1)
        card_r2 = cur_card[0]+str(int(cur_card[1])+2)
        
        # 枚举三种情况
        if dat['avail_cards'].count(card_l2) > 0 and dat['avail_cards'].count(card_l1) > 0:
            dat['avail_cards'].remove(card_l2)
            dat['avail_cards'].remove(card_l1)
            new_score, _ = cal_score(dat['avail_cards'], tables)
            play_card_selected, new_max_score = play_card(dat, tables, policy='table')
            dat['avail_cards'].append(card_l2)
            dat['avail_cards'].append(card_l1)
            if new_max_score >= max_score:
                max_score = new_max_score
                action = "CHI {} {}".format(card_l1, play_card_selected)
                avail_chi_actions.append([0, card_l1, play_card_selected, new_score, new_max_score])
        
        if dat['avail_cards'].count(card_l1) > 0 and dat['avail_cards'].count(card_r1) > 0:
            dat['avail_cards'].remove(card_l1)
            dat['avail_cards'].remove(card_r1)
            new_score, _ = cal_score(dat['avail_cards'], tables)
            play_card_selected, new_max_score = play_card(dat, tables, policy='table')
            dat['avail_cards'].append(card_l1)
            dat['avail_cards'].append(card_r1)
            if new_max_score >= max_score:
                max_score = new_max_score
                action = "CHI {} {}".format(cur_card, play_card_selected)
                avail_chi_actions.append([1, cur_card, play_card_selected, new_score, new_max_score])
        
        if dat['avail_cards'].count(card_r1) > 0 and dat['avail_cards'].count(card_r2) > 0:
            dat['avail_cards'].remove(card_r1)
            dat['avail_cards'].remove(card_r2)
            new_score, _ = cal_score(dat['avail_cards'], tables)
            play_card_selected, new_max_score = play_card(dat, tables, policy='table')
            dat['avail_cards'].append(card_r1)
            dat['avail_cards'].append(card_r2)
            if new_max_score >= max_score:
                max_score = new_max_score
                action = "CHI {} {}".format(card_r1, play_card_selected)
                avail_chi_actions.append([2, card_r1, play_card_selected, new_score, new_max_score])
        
        if len(avail_chi_actions) == 0:
            return False
        else:
            return max_score, action, avail_chi_actions
    
    else:
        raise NotImplementedError


def peng_card(dat, tables, policy='table', reward=0):
    # 碰牌算法，策略可选为 'table', 'search'
    # 若当前request不能碰，直接返回False，否则根据policy做决策
    # table根据打表估值，分别计算碰前/碰后/碰后再出一张牌后avail_cards的估值
    # 另外可以设置碰牌reward来鼓励碰牌带来的番

    # 先判断碰牌是否合法
    cur_card = dat['cur_request'][-1]
    if dat['avail_cards'].count(cur_card) < 2:
        return False

    if policy == 'table':
        # 原始得分
        raw_score, _ = cal_score(dat['avail_cards'], tables)
        # 碰后得分
        dat['avail_cards'].remove(cur_card)
        dat['avail_cards'].remove(cur_card)
        new_score, _ = cal_score(dat['avail_cards'], tables)
        # 碰+出牌后得分
        play_card_selected, new_max_score = play_card(dat, tables, policy='table')

        dat['avail_cards'].append(cur_card)
        dat['avail_cards'].append(cur_card)

        if new_max_score >= raw_score:
            action = "PENG {}".format(play_card_selected)
            return new_max_score, action
        return False

    else:
        raise NotImplementedError


def gang_card_from_other(dat, tables, policy='table'):
    # 杠别人打出的牌

    # 先判断碰牌是否合法
    cur_card = dat['cur_request'][-1]
    if dat['avail_cards'].count(cur_card) < 3:
        return False
    
    if policy == 'table':
        # 原始得分
        raw_score, _ = cal_score(dat['avail_cards'], tables)
        # 杠后得分
        dat['avail_cards'].remove(cur_card)
        dat['avail_cards'].remove(cur_card)
        dat['avail_cards'].remove(cur_card)
        new_score, _ = cal_score(dat['avail_cards'], tables)

        dat['avail_cards'].append(cur_card)
        dat['avail_cards'].append(cur_card)
        dat['avail_cards'].append(cur_card)

        if new_score >= raw_score:
            action = "GANG"
            return new_score, action
        return False

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