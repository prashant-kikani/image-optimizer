# from numba import jit, autojit
import argparse
import os
import math
import numpy as np
from utils import *
from scipy import fftpack
from PIL import Image
from huffman import HuffmanTree
import datetime

def img2arr(image):
    im_arr = np.fromstring(image.tobytes(), dtype=np.uint8)
    dep = (int) (im_arr.size / (image.size[0] * image.size[1]))
    if dep > 1:
        im_arr = im_arr.reshape((image.size[1], image.size[0], dep))
    else:
        im_arr = im_arr.reshape((image.size[1], image.size[0]))
    return im_arr
        

def quantize(block, component):
    q = load_quantization_table(component)
    return (block / q).round().astype(np.int32)


def block_to_zigzag(block):
    return np.array([block[point] for point in zigzag_points(*block.shape)])

# @autojit
def run_length_encode(arr):
    # determine where the sequence is ending prematurely
    last_nonzero = -1
    for i, elem in enumerate(arr):
        if elem != 0:
            last_nonzero = i

    # each symbol is a (RUNLENGTH, SIZE) tuple
    symbols = []

    # values are binary representations of array elements using SIZE bits
    values = []

    run_length = 0

    for i, elem in enumerate(arr):
        if i > last_nonzero:
            symbols.append((0, 0))
            values.append(int_to_binstr(0))
            break
        elif elem == 0 and run_length < 15:
            run_length += 1
        else:
            size = bits_required(elem)
            symbols.append((run_length, size))
            values.append(int_to_binstr(elem))
            run_length = 0
    return symbols, values


def write_to_file(filepath, dc, ac, blocks_count, tables):
    try:
        f = open(filepath, 'w')
    except FileNotFoundError as e:
        raise FileNotFoundError(
                "No such directory: {}".format(
                    os.path.dirname(filepath))) from e

    for table_name in ['dc_y', 'ac_y', 'dc_c', 'ac_c']:

        # 16 bits for 'table_size'
        f.write(uint_to_binstr(len(tables[table_name]), 16))

        for key, value in tables[table_name].items():
            if table_name in {'dc_y', 'dc_c'}:
                # 4 bits for the 'category'
                # 4 bits for 'code_length'
                # 'code_length' bits for 'huffman_code'
                f.write(uint_to_binstr(key, 4))
                f.write(uint_to_binstr(len(value), 4))
                f.write(value)
            else:
                # 4 bits for 'run_length'
                # 4 bits for 'size'
                # 8 bits for 'code_length'
                # 'code_length' bits for 'huffman_code'
                f.write(uint_to_binstr(key[0], 4))
                f.write(uint_to_binstr(key[1], 4))
                f.write(uint_to_binstr(len(value), 8))
                f.write(value)

    # 32 bits for 'blocks_count'
    f.write(uint_to_binstr(blocks_count, 32))

    for b in range(blocks_count):
        for c in range(3):
            category = bits_required(dc[b, c])
            print("D")
            symbols, values = run_length_encode(ac[b, :, c])
            print("E")

            dc_table = tables['dc_y'] if c == 0 else tables['dc_c']
            ac_table = tables['ac_y'] if c == 0 else tables['ac_c']

            f.write(dc_table[category])
            f.write(int_to_binstr(dc[b, c]))

            for i in range(len(symbols)):
                f.write(ac_table[tuple(symbols[i])])
                f.write(values[i])
    f.close()

class JPEGFileReader:
    TABLE_SIZE_BITS = 16
    BLOCKS_COUNT_BITS = 32

    DC_CODE_LENGTH_BITS = 4
    CATEGORY_BITS = 4

    AC_CODE_LENGTH_BITS = 8
    RUN_LENGTH_BITS = 4
    SIZE_BITS = 4

    def __init__(self, filepath):
        self.__file = open(filepath, 'r')

    def read_int(self, size):
        if size == 0:
            return 0

        # the most significant bit indicates the sign of the number
        bin_num = self.__read_str(size)
        if bin_num[0] == '1':
            return self.__int2(bin_num)
        else:
            return self.__int2(binstr_flip(bin_num)) * -1

    # @autojit        
    def read_dc_table(self):
        table = dict()

        table_size = self.__read_uint(self.TABLE_SIZE_BITS)
        for _ in range(table_size):
            category = self.__read_uint(self.CATEGORY_BITS)
            code_length = self.__read_uint(self.DC_CODE_LENGTH_BITS)
            code = self.__read_str(code_length)
            table[code] = category
        return table
    
   # @autojit
    def read_ac_table(self):
        table = dict()

        table_size = self.__read_uint(self.TABLE_SIZE_BITS)
        for _ in range(table_size):
            run_length = self.__read_uint(self.RUN_LENGTH_BITS)
            size = self.__read_uint(self.SIZE_BITS)
            code_length = self.__read_uint(self.AC_CODE_LENGTH_BITS)
            code = self.__read_str(code_length)
            table[code] = (run_length, size)
        return table

    def read_blocks_count(self):
        return self.__read_uint(self.BLOCKS_COUNT_BITS)

    # @autojit
    def read_huffman_code(self, table):
        prefix = ''
        # TODO: break the loop if __read_char is not returing new char
        while prefix not in table:
            prefix += self.__read_char()
        return table[prefix]

    # @autojit
    def __read_uint(self, size):
        if size <= 0:
            raise ValueError("size of unsigned int should be greater than 0")
        return self.__int2(self.__read_str(size))

    def __read_str(self, length):
        return self.__file.read(length)

    def __read_char(self):
        return self.__read_str(1)

    def __int2(self, bin_num):
        return int(bin_num, 2)


def read_image_file(filepath):
    reader = JPEGFileReader(filepath)

    tables = dict()
    for table_name in ['dc_y', 'ac_y', 'dc_c', 'ac_c']:
        if 'dc' in table_name:
            tables[table_name] = reader.read_dc_table()
        else:
            tables[table_name] = reader.read_ac_table()

    blocks_count = reader.read_blocks_count()

    dc = np.empty((blocks_count, 3), dtype=np.int32)
    ac = np.empty((blocks_count, 63, 3), dtype=np.int32)

    for block_index in range(blocks_count):
        for component in range(3):
            dc_table = tables['dc_y'] if component == 0 else tables['dc_c']
            ac_table = tables['ac_y'] if component == 0 else tables['ac_c']

            category = reader.read_huffman_code(dc_table)
            dc[block_index, component] = reader.read_int(category)

            cells_count = 0

            # TODO: try to make reading AC coefficients better
            while cells_count < 63:
                run_length, size = reader.read_huffman_code(ac_table)

                if (run_length, size) == (0, 0):
                    while cells_count < 63:
                        ac[block_index, cells_count, component] = 0
                        cells_count += 1
                else:
                    for i in range(run_length):
                        ac[block_index, cells_count, component] = 0
                        cells_count += 1
                    if size == 0:
                        ac[block_index, cells_count, component] = 0
                    else:
                        value = reader.read_int(size)
                        ac[block_index, cells_count, component] = value
                    cells_count += 1

    return dc, ac, tables, blocks_count


# @autojit
def zigzag_to_block(zigzag):
    # assuming that the width and the height of the block are equal
    rows = cols = int(math.sqrt(len(zigzag)))

    if rows * cols != len(zigzag):
        raise ValueError("length of zigzag should be a perfect square")

    block = np.empty((rows, cols), np.int32)

    for i, point in enumerate(zigzag_points(rows, cols)):
        block[point] = zigzag[i]

    return block


def dequantize(block, component):
    q = load_quantization_table(component)
    return block * q


def main():
    start = datetime.datetime.now()
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="path to the input image")
    # parser.add_argument("output", help="path to the output image")
    args = parser.parse_args()

    input_file = args.input
    # output_file = args.output
    tole = len(input_file)
    poi = 0
    for i in input_file:
        if i != ".":
            poi += 1
        else:
            break
    exte = input_file[poi + 1:]
    print("exte : ", exte)
    image = Image.open(input_file)
    input_file = input_file[:poi]
    or_img = img2arr(image)
    print("original image shape : ", or_img.shape)
    ycbcr = image.convert('YCbCr')
    npmat = np.array(ycbcr, dtype=np.uint8)
    rows, cols = npmat.shape[0], npmat.shape[1]
    orows, ocols = rows, cols
    print("old shape : ", orows, " * ", ocols)
    rows = int(rows / 8) * 8
    cols = int(cols / 8) * 8
    # npmat.reshape((rows, cols, 3)) WRONG
    npmat = npmat[0:rows, 0:cols, :]
    print("new shape : ", npmat.shape[0]," * ", npmat.shape[1])

    # block size: 8x8
    """
    if rows % 8 == cols % 8 == 0:
        blocks_count = rows // 8 * cols // 8
    else:
    	if rows % 8 != 0 and cols % 8 != 0:
    		blocks_count = int(rows / 8) * int(cols / 8)
    """
    print(rows / 8, cols / 8, int(rows / 8), int(cols / 8))
    blocks_count = int(rows / 8) * int(cols / 8)
    		
    # raise ValueError(("the width and height of the image should both be mutiples of 8"))
    print("blocks_count : ", blocks_count)
    # dc is the top-left cell of the block, ac are all the other cells
    dc = np.empty((blocks_count, 3), dtype=np.int32)
    ac = np.empty((blocks_count, 63, 3), dtype=np.int32)
    print("rows", rows, " cols ", cols)
    for i in range(0, rows, 8):
        for j in range(0, cols, 8):
            try:
                block_index += 1
            except NameError:
                block_index = 0

            for k in range(3):
                # split 8x8 block and center the data range on zero
                # [0, 255] --> [-128, 127]
                block = npmat[i:i+8, j:j+8, k] - 128

                dct_matrix = fftpack.dct(block, norm='ortho')
                quant_matrix = quantize(dct_matrix,
                                        'lum' if k == 0 else 'chrom')
                # print("P")
                zz = block_to_zigzag(quant_matrix)
                # print("Q")

                dc[block_index, k] = zz[0]
                ac[block_index, :, k] = zz[1:]
        # print("ENCODING_Outer")
    H_DC_Y = HuffmanTree(np.vectorize(bits_required)(dc[:, 0]))
    H_DC_C = HuffmanTree(np.vectorize(bits_required)(dc[:, 1:].flat))
    H_AC_Y = HuffmanTree(
            flatten(run_length_encode(ac[i, :, 0])[0]
                    for i in range(blocks_count)))
    H_AC_C = HuffmanTree(
            flatten(run_length_encode(ac[i, :, j])[0]
                    for i in range(blocks_count) for j in [1, 2]))

    tables = {'dc_y': H_DC_Y.value_to_bitstring_table(),
              'ac_y': H_AC_Y.value_to_bitstring_table(),
              'dc_c': H_DC_C.value_to_bitstring_table(),
              'ac_c': H_AC_C.value_to_bitstring_table()}

    # print("B")
    print("ENCODING DONE................................................")
    print("time passed : ", ((datetime.datetime.now() - start).seconds) / 60, " minutes")
    # write_to_file(output_file, dc, ac, blocks_count, tables)
    # print("C")
    # assuming that the block is a 8x8 square
    block_side = 8

    # assuming that the image height and width are equal
    # image_side = int(math.sqrt(blocks_count)) * block_side
    # rows = 672
    # cols = 1200

    # blocks_per_line = image_side // block_side

    npmat = np.empty(or_img.shape, dtype=np.uint8)

    """
    for block_index in range(blocks_count):
        i = block_index // blocks_per_line * block_side
        j = block_index % blocks_per_line * block_side

        for c in range(3):
            zigzag = [dc[block_index, c]] + list(ac[block_index, :, c])
            quant_matrix = zigzag_to_block(zigzag)
            dct_matrix = dequantize(quant_matrix, 'lum' if c == 0 else 'chrom')
            block = fftpack.idct(dct_matrix, norm='ortho')
            npmat[i:i+8, j:j+8, c] = block + 128
    """
    # block_index = 0
    i, j = 0, 0
    print("rows : ", rows, " cols : ", cols)
    for i in range(0, rows, 8):
        # print("DECODING_Outer")
        for j in range(0, cols, 8):
            try:
                block_index1 += 1
            except NameError:
                block_index1 = 0

            for c in range(3):
                zigzag = [dc[block_index1, c]] + list(ac[block_index1, :, c])
                quant_matrix = zigzag_to_block(zigzag)
                dct_matrix = dequantize(quant_matrix, 'lum' if c == 0 else 'chrom')
                block = fftpack.idct(dct_matrix, norm='ortho')
                npmat[i:i+8, j:j+8, c] = block + 128

    image = Image.fromarray(npmat, 'YCbCr')
    image = image.convert('RGB')
    npmat[-(orows - rows):,-(ocols - cols):,:] = or_img[-(orows - rows):,-(ocols - cols):,:]
    # image.show()
    print("DONE. time passed : ", ((datetime.datetime.now() - start).seconds) / 60, " minutes")
    output_file = input_file + "_opti_by_pkikani." + exte
    image.save(output_file)

if __name__ == "__main__":
    main()
