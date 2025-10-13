import kinesis_flipmount

#make a main function
def main():
    config = kinesis_flipmount.FlipMountConfig(serial="37004214")  # Auto-pick device
    flipmount = kinesis_flipmount.KinesisFlipMount(config)
    flipmount.open()
    input("Press Enter to close the flip mount...")
    flipmount.close()
    flipmount.disconnect()