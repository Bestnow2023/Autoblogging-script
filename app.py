import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import markdown
from tqdm import tqdm
import base64
import datetime

app = Flask(__name__)
CORS(app)  

# CustomGPT API configuration
load_dotenv()
CUSTOMGPT_API_KEY = os.getenv('CUSTOMGPT_API_KEY')
CUSTOMGPT_API_URL = os.getenv('CUSTOMGPT_API_URL')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# stable diffusion configuration
api_host = 'https://api.stability.ai'
api_key = os.getenv('DREAMSTUDIO_API_KEY')
engine_id = 'stable-diffusion-xl-beta-v2-2-2'

def getModelList():
    url = f"{api_host}/v1/engines/list"
    response = requests.get(url, headers={"Authorization": f"Bearer {api_key}"})

    if response.status_code == 200:
        payload = response.json()
        print(payload)
height = 512
width = 768
steps = 50
files = []
# image generation and upload it to wordpress site. return uploaded image url
def generateStableDiffusionImage(prompt, height, width, steps, username, password, wp_url, code):
    url = f"{api_host}/v1/generation/{engine_id}/text-to-image"
    headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {api_key}"
    }
    payload = {}
    payload['text_prompts'] = [{"text": f"{prompt}"}]
    payload['cfg_scale'] = 7
    payload['clip_guidance_preset'] = 'FAST_BLUE'
    payload['height'] = height
    payload['width'] = width
    payload['samples'] = 1
    payload['steps'] = steps

    response = requests.post(url,headers=headers,json=payload)
    #Processing the response
    if response.status_code == 200:
        data = response.json()
        filename = f'./{datetime.datetime.now().timestamp()}.png'
        for i, image in enumerate(data["artifacts"]):
            with open(f"{datetime.datetime.now().timestamp()}.png", "wb") as f:
                f.write(base64.b64decode(image["base64"]))
        # Prepare the headers for the REST API request
        with open(filename, 'rb') as img:
            headers = {
                'Content-Disposition': f'attachment; filename={os.path.basename(filename)}',
                'Content-Type': 'image/png',  # Adjust this if your images are not PNGs
                'Authorization': 'Basic ' + base64.b64encode(f'{username}:{password}'.encode('utf-8')).decode('utf-8')
            }

            # Send the POST request to the WordPress REST API
            response = requests.post(f'{wp_url}/wp-json/wp/v2/media', headers=headers, data=img)
            files.append(filename)
            
            if response.status_code == 201:
                image_id = response.json()['id']
                image_url = response.json()['link']
                if(code == 1):
                    print(image_id)
                    return image_id
                else:
                    print(image_url)
                    return image_url
            else:
                print(f"Error uploading image: {response.content}")
                exit("image upload failed")

# main part for content and title generation.

def generate_content(prompt):
    headers = {
        "accept": "application/json",
        'Authorization': f'Bearer {CUSTOMGPT_API_KEY}',
        'Content-Type': 'application/json'
    }
    # print(headers)
    data = {
        'prompt': prompt
    }

    response = requests.post(CUSTOMGPT_API_URL, headers=headers, json=data)
    # print(response.text)
    if response.status_code == 200:
        content = response.json()['data']['openai_response']
        # print(content)
        return content
    else:
        return None

# post the content to wordpress site.
def post_to_wordpress(title, content, wordpress_url, featuredimg, username, password):
    post_data = {
        'title': title,
        'content': content,
        'status': 'publish',
        "featured_media": featuredimg
    }
    
    response = requests.post(f"{wordpress_url}/wp-json/wp/v2/posts", auth=(username, password), json=post_data)
    
    if response.status_code == 201:
        return True
    else:
        return False
    
def get_auth_token(username, password, wordpress_url):
    auth_data = {
        "username": username,
        "password": password
    }
    
    auth_url = f"{wordpress_url}/wp-json/jwt-auth/v1/token"
    response = requests.post(auth_url, data=auth_data)
    
    if response.status_code == 200:
        return response.json().get("token", None)
    else:
        print("Failed to obtain authentication token.")
        print(response.text)
        return None
    
# main function that start from here
@app.route('/', methods=['POST'])
def generate_post():
    try:
        # get the data from the post data
        # style
        # {
        #     "username" : "name",
        #     "password" : "your_password",
        #     "url" : "wordpress_site_url",
        #     "content" : "prompt_for_the_blog"
        # }
        data = request.get_json()
        username = data['username']
        password = data['password']
        wordpress_url = data['url']
        # prepare for the prompt
        prompt = "write the outline of a blog post about "
        prompt += data['content']
        prompt += ". This should be like a authoritative comprehensive guide. The title should nested H1 Should include a FAQ and Conclusion at the end. And give me the output as a JSON block with nested H2 and H3 tags indicating the sub-sections. No further explanation is required. Your response contain ONLY the JSON block and nothing else. "

        # generate the outline of the blog and sort it.
        print("generating started!")
        content = generate_content(prompt)
        json_content = json.loads(content)
        # print(json_content)
        h2_with_h3 = []
        for h2_item in json_content["H2"]:
            h2_title = h2_item["title"]
            h3_titles = [h3 for h3 in h2_item["H3"]]
            h2_with_h3.append({"H2 Title": h2_title, "H3 Titles": h3_titles})
        title = json_content["H1"]      # title of the blog
        featuredimg = generateStableDiffusionImage(title, height, width, 30, username, password, wordpress_url, 1)
        # generate the main content of the blog
        tmp = ""
        for index, item in enumerate(tqdm(h2_with_h3, desc='Generating blog posts')):
            tmp += f'## {index + 1}. {item["H2 Title"]}\n\n'        # the sub-title of the blog
            # generate the content for subtitle.
            tmpl = generate_content(f'write an introduction for a section titled \"{item["H2 Title"]}\" in about 100 words. ')
            if tmpl != "I'm sorry, but I can't assist with that.":          # this is for the skip when "I am sorry, but I can't assist with that."
                tmp += tmpl
            tmp += "\n\n\n"
            # prepare the prompt for image generation.
            prompt_img = json_content["H1"]         # prompt for the image = title + sub-title
            prompt_img += f' {item["H2 Title"]}'

            # generate the image
            image_url = generateStableDiffusionImage(prompt_img, height, width, 30, username, password, wordpress_url, 2)     # The image url.

            tmp += f'![Alt Text]({image_url})\n\n'      # add the image to the content.
            # generate the content for each sub-sub title
            for subitem in item["H3 Titles"]:
                if isinstance(subitem, str):
                    tmp += "\n###- " + subitem + "\n\n"
                    tmpl = generate_content(f' I need to write a sub-section titled \"{subitem}\". Please write this sub-section in upto 200 words')
                else:
                    tmp += "\n###- " + subitem["title"] + "\n\n"
                    tmp += generate_content(f' I need to write a sub-section titled \"{subitem["title"]}\". Please write this sub-section in upto 200 words')
                if tmpl != "I'm sorry, but I can't assist with that.":          # this is for the skip when "I am sorry, but I can't assist with that."
                    tmp += tmpl
                tmp += "\n\n"

        # make the html code from the generated blog
        html_content = markdown.markdown(tmp)

        # convert the string to json data
        tmpdata = {
            "content": html_content
        }
        json_data = json.dumps(tmpdata['content'], indent=4)

        # post it.
        post_to_wordpress(title, html_content, wordpress_url, featuredimg, username, password)
        for filename in files:
            try:
                os.remove(filename)
                print(f"File '{filename}' deleted successfully.")
            except OSError as e:
                print(f"Error deleting file '{filename}': {e}")
        return jsonify({'success' : 'Your blog is posted successfully!'})
    
        file_path = "my_html_file.html"
        with open(file_path, "w") as f:
            f.write(html_content)
        return 'success'
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0')
