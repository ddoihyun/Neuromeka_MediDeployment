import common as Common


class PalletManager(metaclass=Common.SingletonMeta):
    def __init__(self) -> None:
        super().__init__()


    def save_pallet_maker_list(self, pallet_maker_list: dict):
        Common.Utils.write_json(Common.Config().PALLET_MAKER_DIR, pallet_maker_list)

    def load_pallet_maker_list(self) -> dict:
        return Common.Utils.load_json(Common.Config().PALLET_MAKER_DIR)

    def get_pallet_name_list(self):
        pallet_maker_list = self.load_pallet_maker_list()
        name_list = []
        if pallet_maker_list:
            for pallet_maker in pallet_maker_list['pallet_makers']:
                name_list.append(pallet_maker['name'])
        return name_list

    def get_pallet(self, name):
        pallet_maker_list = self.load_pallet_maker_list()

        target_pallet_maker = None
        if pallet_maker_list:
            for pallet_maker in pallet_maker_list['pallet_makers']:
                if name == pallet_maker['name']:
                    target_pallet_maker = pallet_maker
                    break

        if target_pallet_maker is None:
            raise Exception("There are no named {}".format(name))
        elif target_pallet_maker['pallet_pattern'] > 3:
            raise Exception("The selected pattern cannot be used {}".format(target_pallet_maker['pallet_pattern']))
        else:
            pallet_pattern = target_pallet_maker['pallet_pattern']
            m = target_pallet_maker['width_num']
            n = target_pallet_maker['height_num']

            tpos = []
            for i in range(Common.Config().ROBOT_DOF):
                tpos.append(target_pallet_maker['tpos0'][i])
            for i in range(Common.Config().ROBOT_DOF):
                tpos.append(target_pallet_maker['tpos1'][i])
            for i in range(Common.Config().ROBOT_DOF):
                tpos.append(target_pallet_maker['tpos2'][i])

            jpos = []
            for i in range(Common.Config().ROBOT_DOF):
                jpos.append(target_pallet_maker['jpos0'][i])
            for i in range(Common.Config().ROBOT_DOF):
                jpos.append(target_pallet_maker['jpos1'][i])
            for i in range(Common.Config().ROBOT_DOF):
                jpos.append(target_pallet_maker['jpos2'][i])

            return tpos, pallet_pattern, m, n, jpos
