import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import json
import os
from pathlib import Path
import requests

from rdflib import URIRef
from tqdm import tqdm
# import slack

from ocr.google_ocr import get_text_from_image
from ocr.image_list import get_volumes_for_work
from ocr.image_list import get_simple_imagelist_for_vol
from ocr.image_list import get_iiif_fullimg_for_filename
from ocr.image_list import shorten


# PAGE_BREAK = '\n' + '#'*100 + '\n'

# client = slack.WebClient(token=os.environ['SLACK_API_TOKEN'])


# def slack_notifier(message, msg_type='info'):
#     response = client.chat_postMessage(
#         channel='#google-ocr',
#         text=f"[INFO] {message}" if msg_type=='info' else f"[ERROR] {message}"
#    )


def get_image(img_url):
    response = requests.get(img_url)
    img = response.content
    return img

def get_work_ids(fn):
    for work_id in fn.read_text().split('\n'):
        if not work_id: continue
        yield work_id, URIRef(f'http://purl.bdrc.io/resource/{work_id}')


def is_img_ocred_general(path, img_num):
    json_output_fn_old = path/f'{img_num:03}.json'
    json_output_fn_new = path/f'{img_num:04}.json'
    return json_output_fn_new.is_file() or json_output_fn_old.is_file()


def get_img_num(url):
    url_part = url.split('::')[1]
    img_num_sep = '<none>'
    if '.tif' in url_part: img_num_sep = '.tif'
    elif '.JPG' in url_part: img_num_sep = '.JPG'
    img_id = url_part.split(img_num_sep)[0]
    img_num = int(img_id[-4:])
    return img_num


def run_ocr(vol_id, img_info):
    img_url = get_iiif_fullimg_for_filename(vol_id, img_info["filename"])
    img_num = get_img_num(img_url)
    
    # check if img is ocred
    if is_img_ocred(img_url): return
    
    img = get_image(img_url)
    response_json = get_text_from_image(img)
    response_dict = eval(response_json)
    response_dict['image_link'] = img_url
    print(f'[INfo] Volume {shorten(vol_id)} -> image: {img_num} ... completed')
    return response_dict


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--input', '-i', help='path to workids file')
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path('./output')
    output_path.mkdir(exist_ok=True)



    # slack_notifier('Google OCR is running...')

    for workid_path in input_path.iterdir():
        # go through all the URIRef workids 
        for work_id, work_uri in get_work_ids(workid_path):

            print(f'[INfo] Work {work_id} processing ....')

            # create work directory
            work_dir = output_path/work_id
            work_dir.mkdir(exist_ok=True)
            # get all the volumes for the work
            for vol_info in get_volumes_for_work(work_uri):
                vol_id = vol_info["volumeId"]
                print(f'[INfo] volume {shorten(vol_id)} processing ....')

                vol_dir = work_dir/shorten(vol_id)
                vol_dir.mkdir(exist_ok=True)

                # check if vol is ocred
                vol_resource = vol_dir/'resources'
                vol_resource.mkdir(exist_ok=True)

                is_img_ocred = is_img_ocred_general(vol_resource)

                vol_run_ocr = partial(run_ocr, vol_id)
                try:
                    # run ocr in parallel on images of the volume
                    with ProcessPoolExecutor() as executor:
                        responses = executor.map(
                            vol_run_ocr,
                            get_simple_imagelist_for_vol(vol_id)
                        )
                except:
                    slack_notifier(f'Failed at {work_id}:{vol_id}')
                print(f'[INFO] Volume {shorten(vol_id)} is completed !')

                # text = ''
                # vol_text_fn = vol_dir/'base.txt'
                for i, res in enumerate(responses):
                    # accumulate all the page text
                    if not res: continue # blank page response is empty
                    # page_text = res['textAnnotations'][0]['description']
                    # text += page_text + PAGE_BREAK

                    # save each page ocr json reponse separately
                    page_path_json = vol_resource/f'{i+1:04}.json'
                    json.dump(res, page_path_json.open('w'))

    # slack_notifier('Google OCR has completed !')
    # slack_notifier("Don't forget to stop the VM instance !")
                
                # save the text
                # vol_text_fn.write_text(text)