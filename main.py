from fastapi import FastAPI, Request, HTTPException, status, Depends
from tortoise.contrib.fastapi import register_tortoise
from models import *
from authentication import *
from fastapi.security import (
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm
)
from tortoise.signals import  post_save 
from typing import List, Optional, Type
from tortoise import BaseDBAsyncClient
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from emails import *
import templates
from pathlib import Path

from fastapi import File, UploadFile
import secrets
from fastapi.staticfiles import StaticFiles
from PIL import Image



app = FastAPI()

oath2_scheme = OAuth2PasswordBearer(tokenUrl = 'token')

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post('/token')
async def generate_token(request_form: OAuth2PasswordRequestForm = Depends()):
    token = await token_generator(request_form.username, request_form.password)
    return {'access_token' : token, 'token_type' : 'bearer'}

async def get_current_user(token: str = Depends(oath2_scheme)):
    try:
        payload = jwt.decode(token, config_credentials['SECRET'], algorithms = ['HS256'])
        user = await User.get(id = payload.get("id"))
    except:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await user

@app.post("/user/me")
async def user_login(user: user_pydanticIn = Depends(get_current_user)):
    business = await Business.get(owner = user)
    logo = business.logo
    logo = "localhost:8000/static/images/"+logo
    return {
        "status": "ok",
        "data": 
        {
            "username": user.username,
            "email": user.email,
            "verified": user.is_verified,
            "joined date": user.join_date.strftime("%b %d %Y"),
            "logo": logo
        }
    }

@post_save(User)
async def create_business(
    sender: "Type[User]",
    instance: User,
    created: bool,
    using_db: "Optional[BaseDBAsyncClient]",
    update_fields: List[str]) -> None:
    
    if created:
        business_obj = await Business.create(
                business_name = instance.username, owner = instance)
        await business_pydantic.from_tortoise_orm(business_obj)
        # await send_email([instance.email], instance)

@app.post('/registration')
async def user_registration(user: user_pydanticIn):
    # breakpoint()
    user_info = user.dict(exclude_unset = True)
    user_info['password'] = get_password_hash(user_info['password'])
    user_obj = await User.create(**user_info)
    new_user = await user_pydantic.from_tortoise_orm(user_obj)
 
    return {"status" : "ok", 
            "data" : 
                f"Hello {new_user.username} thanks for choosing our services. Please check your email inbox and click on the link to confirm your registration."} 

template_dir = "C:\\Users\\NH2882\\Desktop\\revision\\templates"
templates = Jinja2Templates(directory=str(template_dir))
@app.get('/verification', response_class=HTMLResponse)
async def email_verification(request: Request, token: str):
    user = await verify_token(token)
    if user and not user.is_verified:
        user.is_verified = True
        await user.save()
        return templates.TemplateResponse("verification.html", {"request": request, "username": user.username})

    raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

@app.post("/uploadfile/profile")
async def create_upload_file(file: UploadFile = File(...), 
                                user: user_pydantic = Depends(get_current_user)):
    FILEPATH = "./static/images/"
    filename = file.filename
    extension = filename.split(".")[1]

    if extension not in ["jpg", "png"]:
        return {"status" : "error", "detail" : "file extension not allowed"}

    token_name = secrets.token_hex(10)+"."+extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()
    with open(generated_name, "wb") as file:
        file.write(file_content)


    # pillow
    img = Image.open(generated_name)
    img = img.resize(size = (200,200))
    img.save(generated_name)

    file.close()

    business = await Business.get(owner = user)
    owner = await business.owner

    if owner == user:
        business.logo = token_name
        await business.save()
    
    else:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Not authenticated to perform this action",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    file_url = "localhost:8000" + generated_name[1:]
    return {"status": "ok", "filename": file_url}

@app.post("/uploadfile/product/{id}")
async def create_upload_file(id: int, file: UploadFile = File(...), 
                                user: user_pydantic = Depends(get_current_user)):
    FILEPATH = "./static/images/"
    filename = file.filename
    extension = filename.split(".")[1]

    if extension not in ["jpg", "png"]:
        return {"status" : "error", "detail" : "file extension not allowed"}

    token_name = secrets.token_hex(10)+"."+extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()
    with open(generated_name, "wb") as file:
        file.write(file_content)


    # pillow
    img = Image.open(generated_name)
    img = img.resize(size = (200,200))
    img.save(generated_name)

    file.close()

    product = await Product.get(id = id)
    business = await product.business
    owner = await business.owner

    if owner == user:
        product.product_image = token_name
        await product.save()
    
    else:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Not authenticated to perform this action",
            headers={"WWW-Authenticate": "Bearer"},
        )


    file_url = "localhost:8000" + generated_name[1:]
    return {"status": "ok", "filename": file_url}
    
@app.post("/products")
async def add_new_product(product: product_pydanticIn, 
                            user: user_pydantic = Depends(get_current_user)):
    product = product.dict(exclude_unset = True)
    
    if product['original_price'] > 0:
        product["percentage_discount"] = ((product["original_price"] - product['new_price'] )/ product['original_price']) * 100

    product_obj = await Product.create(**product, business = user)
    product_obj = await product_pydantic.from_tortoise_orm(product_obj)
    return {"status" : "ok", "data" : product_obj}


@app.get("/products")
async def get_products():
    response = await product_pydantic.from_queryset(Product.all())
    return {"status" : "ok", "data" : response}


@app.get("/products/{id}")
async def specific_product(id: int):
    product = await Product.get(id = id)
    business = await product.business
    owner = await business.owner
    response = await product_pydantic.from_queryset_single(Product.get(id = id))
    print(type(response))
    return {"status" : "ok",
            "data" : 
                    {
                    "product_details" : response,
                    "business_details" : {
                    "name" : business.business_name,
                    "city" : business.city,
                    "region" : business.region,
                    "description" : business.business_description,
                    "logo" : business.logo,
                    "owner_id" : owner.id,
                    "email" : owner.email,
                    "join_date" :  owner.join_date.strftime("%b %d %Y")
                        }
                    }
            }

@app.delete("/products/{id}")
async def delete_product(id: int, user: user_pydantic = Depends(get_current_user)):
    product = await Product.get(id = id)
    business =  await product.business
    owner = await business.owner
    if user == owner:
        product.delete()
    else:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Not authenticated to perform this action",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"status" : "ok"}

@app.put("/product/{id}")
async def update_product(id: int, update_info: product_pydanticIn, user: user_pydantic = Depends(get_current_user)):
    product = await Product.get(id=id)
    business = await product.business
    owner = await business.owner

    update_info = update_info.dict(exclude_unset = True)
    update_info["date_published"] =  datetime.utcnow()
    if user == owner and update_info["original_price"]>0:
        update_info["percentage_discount"] = ((update_info["original_price"] - update_info["new_price"])/update_info["original_price"])*100
        
        product = await product.update_from_dict(update_info)
        await product.save()
        response = await product_pydantic.from_tortoise_orm(product)
        return {"status": "ok", "date": response}
    
    else:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Not authenticated to perform this action",
            headers={"WWW-Authenticate": "Bearer"},
        )


register_tortoise(
    app,
    db_url="sqlite://database.sqlite3",
    modules={"models": ["models"]},
    generate_schemas=True,
    add_exception_handlers=True
)
