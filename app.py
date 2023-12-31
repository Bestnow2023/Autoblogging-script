import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_cors import CORS
import json
import markdown
from tqdm import tqdm
import base64
import datetime
from waitress import serve

app = Flask(__name__)
CORS(app)  

# CustomGPT API configuration

api_host = 'https://api.stability.ai'
engine_id = 'stable-diffusion-xl-beta-v2-2-2'

height = 512
width = 768
steps = 50
files = []
count = 0
# image generation and upload it to wordpress site. return uploaded image url
def generateStableDiffusionImage(prompt, height, width, steps, username, password, wp_url, code, dream_api_key):
    url = f"{api_host}/v1/generation/{engine_id}/text-to-image"
    headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {dream_api_key}"
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
        filename = f'{datetime.datetime.now().timestamp()}.png'
        for i, image in enumerate(data["artifacts"]):
            with open(f"{datetime.datetime.now().timestamp()}.png", "wb") as f:
                f.write(base64.b64decode(image["base64"]))
                filename=f.name
                #for test
                # return filename
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
                        return image_id
                    else:
                        return image_url
                else:
                    print(f"Error uploading image: {response.content}")
                    exit("image upload failed")

# main part for content and title generation.
def generate_conversation(customgpt_api_key):
    url = "https://app.customgpt.ai/api/v1/projects/10825/conversations"

    payload = { "name": "blogpost" }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {customgpt_api_key}"
    }

    response = requests.post(url, json=payload, headers=headers)

    new_guid = json.loads(response.text)['data']['session_id']
    return f"https://app.customgpt.ai/api/v1/projects/10825/conversations/{new_guid}/messages?stream=false&lang=en"

def generate_content(CUSTOMGPT_API_URL, prompt, api_key):
    headers = {
        "accept": "application/json",
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    data = {
        'prompt': prompt
    }

    response = requests.post(CUSTOMGPT_API_URL, headers=headers, json=data)
    if response.status_code == 200:
        content = response.json()['data']['openai_response']
        return content
    else:
        return None

# post the content to wordpress site.
def post_to_wordpress(title, content, wordpress_url, featuredimg, username, password):
    if featuredimg == '':
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish',
        }
    else:
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
@app.route('/create', methods=['POST'])
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
        count = 0
        counter = 0
        data = request.get_json()
        username = data['username']
        password = data['password']
        wordpress_url = data['url']
        dream_api_key = data['dreamstudio_api_key']
        featuredimg = ""
        customgpt_api_key = data['customgpt_api_key']
        wordpress = True
        usedream = True
        CUSTOMGPT_API_URL = generate_conversation(customgpt_api_key)
        print(CUSTOMGPT_API_URL)
        # return jsonify({"success":"success"})
        if username == '' or password == '' or wordpress_url == '':
            wordpress = False
        if dream_api_key == '':
            usedream = False
        print(data['dreamstudio_api_key'])
        # prepare for the prompt
        prompt = "write the outline of a blog post about "
        prompt += f'"{data["content"]}"'
        prompt += ". This should be like a authoritative comprehensive guide. Should include a FAQ and Conclusion at the end. And give me the output as a JSON block with nested H2 and H3 tags indicating the sub-sections. No further explanation is required.  Your response contain ONLY the JSON block and nothing else. "

        # generate the outline of the blog and sort it.
        print("Thinking...")
        
        content = generate_content(CUSTOMGPT_API_URL, prompt, customgpt_api_key)
        json_content = json.loads(content)
        if usedream:
            count += len(json_content["H2"]) + 1
        count += len(json_content["H2"])
        for mmk in json_content["H2"]:
            if mmk["title"] != "FAQ":
                count += len(mmk["H3"])
        count += 5
        # print(count)
        h2_with_h3 = []
        for h2_item in json_content["H2"]:
            h2_title = h2_item["title"]
            h3_titles = [h3 for h3 in h2_item["H3"]]
            h2_with_h3.append({"H2 Title": h2_title, "H3 Titles": h3_titles})
        title = json_content["H1"]      # title of the blog
        if usedream:
            featuredimg = generateStableDiffusionImage(f'Fine art photography. An ultra high resolution photo. {title}. Canon EOS R6.', height, width, 30, username, password, wordpress_url, 1, dream_api_key)
            counter += 1
            print(f'{int((counter / count) * 100)}% generated!')
        # generate the main content of the blog
        tmp = ""
        for index, item in enumerate(h2_with_h3):
            tmp += f'## {index + 1}. {item["H2 Title"]}\n\n'        # the sub-title of the blog
            # generate the content for subtitle.
            # print(f'--------------------------> debug1 {item}')
            if item["H2 Title"] != "FAQ":
                tmpl = generate_content(CUSTOMGPT_API_URL, f'In a blog post about "{title}" write an introduction for a H2 sub-section titled "{item["H2 Title"]}" in about 100 words.Write in the first person and incorporate experiences from the CONTEXT. Please do NOT include a conclusion or explanation. Get straight to the point about "{item["H2 Title"]}". If you are able to include quotes and expert points of view gleaned from the CONTEXT, that is preferred.', customgpt_api_key)
                
                # print(f'----------------------------->debug1.5 {tmpl}')
                counter += 1
                print(f'{int((counter / count) * 100)}% generated!')
                if tmpl != "I'm sorry, but I can't assist with that.":          # this is for the skip when "I am sorry, but I can't assist with that."
                    if "H2_SUBHEADING" in tmpl:
                        json_tmpl = json.loads(tmpl)
                        tmp += json_tmpl["H2_SUBHEADING"]
                        # print(f'tmpl is object --------- {json_tmpl["H2_SUBHEADING"]}')
                    else:
                        # print("Tmpl is string")
                        tmp += tmpl
                tmp += "\n\n\n"
                # prepare the prompt for image generation.
                prompt_img = "Fine art photography. An ultra high resolution photo. "        # prompt for the image = title + sub-title
                prompt_img += f' "{item["H2 Title"]}". Canon EOS R6.'
                # print(f"-----------------> for debug2 {prompt_img}")
                # generate the image
                if usedream:
                    image_url = generateStableDiffusionImage(prompt_img, height, width, 30, username, password, wordpress_url, 2, dream_api_key)     # The image url. 
                    tmp += f'![Alt Text]({image_url})\n\n'      # add the image to the content.

                counter += 1
                print(f'{int((counter / count) * 100)}% generated!')

                # generate the content for each sub-sub title
                for subitem in item["H3 Titles"]:
                    if isinstance(subitem, str):
                        tmp += "\n###- " + subitem + "\n\n"
                        tmpl = generate_content(CUSTOMGPT_API_URL, f' In a blog post about "{subitem}" I have a H2 sub-section "{item["H2 Title"]}". please write a H3 sub-section "{subitem}" in upto 200 words. Write in the first person and incorporate experiences from the CONTEXT. Please do NOT include an introduction, conclusion or explanation. Get straight to the point. If you are able to include quotes and expert points of view gleaned from the CONTEXT, that is preferred.', customgpt_api_key)
                        
                        counter += 1
                        print(f'{int((counter / count) * 100)}% generated!')

                    else:
                        tmp += "\n###- " + subitem["title"] + "\n\n"
                        tmpl = generate_content(CUSTOMGPT_API_URL, f' In a blog post about "{subitem["title"]}" I have a H2 sub-section "{item["H2 Title"]}". please write a H3 sub-section "{subitem["title"]}" in upto 200 words. Write in the first person and incorporate experiences from the CONTEXT. Please do NOT include an introduction, conclusion or explanation. Get straight to the point. If you are able to include quotes and expert points of view gleaned from the CONTEXT, that is preferred.', customgpt_api_key)
                        
                        counter += 1
                        print(f'{int((counter / count) * 100)}% generated!')

                    if "sorry" not in tmpl.lower():          # this is for the skip when "I am sorry, but I can't assist with that."
                        tmp += tmpl
                    tmp += "\n\n"
            else:
                prompt_img = f'FAQ in {title}'
                # generate the image
                if usedream:
                    image_url = generateStableDiffusionImage(prompt_img, height, width, 30, username, password, wordpress_url, 2, dream_api_key)     # The image url.
                    tmp += f'![Alt Text]({image_url})\n\n'      # add the image to the content.

                    counter += 1
                    print(f'{int((counter / count) * 100)}% generated!')

                tmpl = generate_content(CUSTOMGPT_API_URL, f'write 5 FAQ questions for a blog post about "{title}". The questions should be for a authoritative comprehensive guide. please give me the output as a JSON block with each question as a element in the JSON array. No further explanation is required. Your response contain ONLY the JSON block and nothing else.', customgpt_api_key)
                
                counter += 1
                print(f'{int((counter / count) * 100)}% generated!')
                json_tmpl = json.loads(tmpl)
                # print(f'------------------------> debug FAQ{json_tmpl}')
                for subitem in json_tmpl:
                    tmp += "\n###- " + subitem["question"] + "\n\n"
                    
                    tmpl = generate_content(CUSTOMGPT_API_URL, f' Write the answer for this question "{subitem["question"]} about {title}".', customgpt_api_key)
                    
                    counter += 1
                    print(f'{int((counter / count) * 100)}% generated!')

                    if "sorry" not in tmpl.lower():        # this is for the skip when "I am sorry, but I can't assist with that."
                        tmp += tmpl
                    tmp += "\n\n"
                tmp += "\n\n\n"
                # prepare the prompt for image generation.

        # make the html code from the generated blog
        html_content = markdown.markdown(tmp)

        # convert the string to json data
        tmpdata = {
            "content": html_content
        }
        # json_data = json.dumps(tmpdata['content'], indent=4)
        #for test write the html file
        # with open("index.html", "w") as htm:
        #     htm.write(html_content)
        #     print('Your blog is posted successfully!')
        #     return "DDDDD"
        # post it.
        if wordpress:
            post_to_wordpress(title, html_content, wordpress_url, featuredimg, username, password)
        for filename in files:
            try:
                os.remove(filename)
            except OSError as e:
                print(f"Error deleting file '{filename}': {e}")
        print('Your blog is posted successfully!')
        return jsonify({'success' : 'Your blog is posted successfully!', 'content': html_content})
    
    except Exception as e:
        print(str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/delete', methods=['POST'])
def delete():
    data = request.get_json()
    username = data['username']
    password = data['password']
    wordpress_url = data['url']
    post_id = data['post_id']
    response = requests.delete(f"{wordpress_url}/wp-json/wp/v2/posts/{post_id}", auth=(username, password))

    if response.status_code == 200:
        return jsonify({"success": "The post was deleted successfully."})
    else:
        return jsonify(({'error'}))

@app.route('/update', methods=['POST'])
def update():
    data = request.get_json()
    username = data['username']
    password = data['password']
    wordpress_url = data['url']
    post_id = data['post_id']
    post_data = data['data']
    new_data = {'content':post_data}
    response = requests.put(f"{wordpress_url}/wp-json/wp/v2/posts/{post_id}", auth=(username, password), json=new_data)

    if response.status_code == 200:
        return jsonify({"success": "The post was deleted successfully."})
    else:
        return jsonify(({'error'}))

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    username = data['username']
    password = data['password']
    wordpress_url = data['url']
    post_id = data['post_id']
    response = requests.get(f"{wordpress_url}/wp-json/wp/v2/posts/{post_id}", auth=(username, password))
    jsondata = json.loads(response.content)

    print(jsondata['content']['rendered'])
    if response.status_code == 200:
        return jsondata['content']['rendered']
    else:
        return jsonify({'error'})


if __name__ == '__main__':
    print("App started")
    serve(app, host="0.0.0.0", port=8080)
    # app.run()
