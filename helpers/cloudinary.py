from cloudinary.uploader import upload


async def upload_image(image_id: str, image):
    result = upload(file=image, public_id=image_id, overwrite=False)
    return result.get("secure_url")
