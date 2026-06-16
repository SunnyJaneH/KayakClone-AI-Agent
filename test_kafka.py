from kafka.memory_kafka import MemoryKafka

kafka = MemoryKafka(data_dir='../data/mock')
sizes = kafka.get_queue_sizes()
print(f'Queue sizes: {sizes}')
print(f'Successfully loaded {sizes["listings"]} listings!')