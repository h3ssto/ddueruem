from ctypes import *

import re

from .Adapter import *
from utils.IO import log_info, blue, hash_hex
from config import *

name        = "BuDDy 2.4"
stub        = "buddy"
url         = "https://sourceforge.net/projects/buddy/files/buddy/BuDDy%202.4/buddy-2.4.tar.gz/download"
archive     = f"{CACHE_DIR}/buddy-2.4.tar.gz"
archive_md5 = "3b59cb073bcb3f26efdb851d617ef2ed"
source_dir  = f"{CACHE_DIR}/buddy-2.4"
shared_lib  = "libbuddy.so"

configure_params = "CFLAGS=-fPIC -std=c99"

hint_install = "--install buddy"

class BUDDY_Adapter():

    def __enter__(self):
        verify_lib(shared_lib, hint_install)

        buddy = CDLL(f"./{shared_lib}")

        self.increase = 100000
        buddy.bdd_init(1000000, 10000000)
        buddy.bdd_setminfreenodes(33)
        buddy.bdd_setmaxincrease(c_int(self.increase))

        self.buddy = buddy

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        buddy = self.buddy
        buddy.bdd_done()

    def name():
        return name

    @staticmethod
    def install(clean = False):
        if clean:
            log_info(f"Clean installing {blue(name)}")
        else:
            log_info(f"Installing {blue(name)}")

        install_library(name, stub, url, archive, archive_md5, source_dir, shared_lib, configure_params, clean)
        log_info()

    def format_cache(self, cnf, filename_bdd):
        with open(filename_bdd, "r") as file:
            content = file.read()

        lines = re.split("[\n\r]",content)

        n_nodes, n_vars = re.split(r"\s+", lines[0].strip())
        var2order = [int(x) for x in re.split(r"\s+", lines[1].strip())]

        order = [0 for _ in range(0, len(var2order))]
        for i,x in enumerate(var2order):
            order[x] = i+1

        nodes = {}
        root = None

        for line in lines[2:]:
            m = re.match(r"(?P<id>\d+) (?P<var>\d+) (?P<low>\d+) (?P<high>\d+)", line)
            if m:
                nodes[int(m["id"])] = (int(m["var"]), int(m["low"]), int(m["high"]))
                root = int(m["id"])

        ids = sorted([x for x in nodes.keys()])

        content = [
            f"input_file:{cnf.filename}",
            f"input_hash:{hash_hex(cnf.filename)}",
            f"order:{','.join([str(x) for x in order])}",
            f"n_vars:{n_vars}",
            f"n_nodes:{n_nodes}",
            f"root:{root}"
        ]

        for i in ids:
            var, low, high = nodes[i]
            content.append(f"{i} {var} 0:{low} 0:{high}")

        with open(filename_bdd, "w") as file:
            file.write(f"{os.linesep}".join(content))
            file.write(os.linesep)

    def deref(*vars):
        buddy = self.buddy

        for x in vars:
            buddy.bdd_delref(x)

    def bdd_and(x, y, deref_operands = False):
        buddy = self.buddy

        z = buddy.bdd_and(x,y)
        buddy.bdd_addref(z)

        if deref_operands:
            deref(x, y)

        return z

    def bdd_or(x, y):
        buddy = self.buddy

        z = buddy.bdd_or(x,y)
        buddy.bdd_addref(z)

        if deref_operands:
            deref(x,y)

        return z

    def from_cnf(self, cnf, order, filename_bdd):
        buddy = self.buddy
        increase = self.increase

        buddy.bdd_setvarnum(cnf.nvars)

        # Normalize as BuDDy indexes from 0
        order = [x - 1 for x in order]   
        arr = (c_uint * len(order))(*order)

        buddy.bdd_setvarorder(byref(arr))
        buddy.bdd_disable_reorder()

        full = None
        n = 0

        for clause in cnf.clauses:
            n+=1

            if full:
                increase = int(max(increase, buddy.bdd_nodecount(full) / 10))
                increase = min(increase, 2500000)
                buddy.bdd_setmaxincrease(c_int(increase))

            log_info(clause, f"({n} / {len(cnf.clauses)})")
            
            cbdd = None

            for x in clause:
                if x < 0:
                    x = abs(x) - 1
                    if cbdd is None:
                        cbdd = buddy.bdd_nithvar(x)
                    else:
                        old = cbdd
                        cbdd = buddy.bdd_addref(buddy.bdd_or(cbdd, buddy.bdd_nithvar(x)))
                        buddy.bdd_delref(old)
                else:
                    x -= 1
                    if cbdd is None:
                        cbdd = buddy.bdd_ithvar(x)
                    else:
                        old = cbdd
                        cbdd = buddy.bdd_addref(buddy.bdd_or(cbdd, buddy.bdd_ithvar(x)))
                        buddy.bdd_delref(old)

            if full is None:
                full = cbdd
            else:
                old = full
                full = buddy.bdd_addref(buddy.bdd_and(full, cbdd))

                buddy.bdd_delref(cbdd)

        buddy.bdd_setvarorder(byref(arr))

        if filename_bdd:
            buddy.bdd_fnsave(c_char_p(filename_bdd.encode("utf-8")), full)

            self.format_cache(cnf, filename_bdd)            

            log_info("BDD saved to", blue(filename_bdd))