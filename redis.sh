#!/bin/bash

# Redis Monitoring Script for Ubuntu/WSL
# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

CONTAINER_NAME="odoomulti-tenantsystem-redis-1"

# Function to print colored headers
print_header() {
    echo -e "${GREEN}=== $1 ===${NC}"
    echo
}

print_subheader() {
    echo -e "${YELLOW}$1:${NC}"
}

# Function to format key-value pairs
format_kv() {
    printf "  %-30s: %s\n" "$1" "$2"
}

# Function to run docker commands - handles both WSL integrated and Windows host Docker
run_docker() {
    if command -v docker &> /dev/null; then
        # Docker is available in WSL
        docker "$@"
    elif command -v docker.exe &> /dev/null; then
        # Use Windows Docker from WSL
        docker.exe "$@"
    else
        echo -e "${RED}Error: Docker not found. Please install Docker Desktop with WSL integration.${NC}"
        exit 1
    fi
}

# Check if container is running
if ! run_docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}Error: Container ${CONTAINER_NAME} is not running${NC}"
    echo -e "${YELLOW}Available containers:${NC}"
    run_docker ps --format "table {{.Names}}\t{{.Status}}"
    exit 1
fi

print_header "REDIS SERVER OVERVIEW"

# Get Redis info sections
SERVER_INFO=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw INFO server)
MEMORY_INFO=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw INFO memory)
CPU_INFO=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw INFO cpu)
CLIENTS_INFO=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw INFO clients)
STATS_INFO=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw INFO stats)
KEYSPACE_INFO=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw INFO keyspace)

# Parse server information
print_subheader "SERVER INFO"
echo "$SERVER_INFO" | grep -E "(redis_version|uptime_in_seconds|tcp_port|os|arch_bits)" | while IFS=':' read -r key value; do
    case $key in
        "uptime_in_seconds")
            uptime_days=$((value / 86400))
            uptime_hours=$(((value % 86400) / 3600))
            uptime_mins=$(((value % 3600) / 60))
            format_kv "$key" "$value (${uptime_days}d ${uptime_hours}h ${uptime_mins}m)"
            ;;
        *)
            format_kv "$key" "$value"
            ;;
    esac
done

echo

# Parse memory information
print_subheader "MEMORY USAGE"
echo "$MEMORY_INFO" | grep -E "(used_memory_human|used_memory_peak_human|used_memory_rss_human|mem_fragmentation_ratio|used_memory_dataset|used_memory_overhead)" | while IFS=':' read -r key value; do
    format_kv "$key" "$value"
done

echo

# Parse CPU information
print_subheader "CPU USAGE"
echo "$CPU_INFO" | grep -E "(used_cpu_sys|used_cpu_user|used_cpu_sys_children|used_cpu_user_children)" | while IFS=':' read -r key value; do
    format_kv "$key" "${value}s"
done

echo

# Parse client information
print_subheader "CLIENT CONNECTIONS"
echo "$CLIENTS_INFO" | grep -E "(connected_clients|client_recent_max_input_buffer|client_recent_max_output_buffer|blocked_clients)" | while IFS=':' read -r key value; do
    format_kv "$key" "$value"
done

echo

print_header "ACTIVE CLIENT CONNECTIONS"

# Get detailed client list
CLIENT_LIST=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw CLIENT LIST)

if [ -n "$CLIENT_LIST" ]; then
    printf "  %-5s %-20s %-8s %-15s %-10s %-15s %s\n" "ID" "Address" "Age" "Command" "Memory" "Database" "Name"
    printf "  %s\n" "$(printf '%*s' 85 '' | tr ' ' '-')"
    
    echo "$CLIENT_LIST" | while read -r line; do
        if [ -n "$line" ]; then
            # Extract fields using grep and sed
            id=$(echo "$line" | grep -o 'id=[0-9]*' | cut -d'=' -f2)
            addr=$(echo "$line" | grep -o 'addr=[^[:space:]]*' | cut -d'=' -f2)
            age=$(echo "$line" | grep -o 'age=[0-9]*' | cut -d'=' -f2)
            cmd=$(echo "$line" | grep -o 'cmd=[^[:space:]]*' | cut -d'=' -f2)
            mem=$(echo "$line" | grep -o 'tot-mem=[0-9]*' | cut -d'=' -f2)
            db=$(echo "$line" | grep -o 'db=[0-9]*' | cut -d'=' -f2)
            name=$(echo "$line" | grep -o 'name=[^[:space:]]*' | cut -d'=' -f2)
            
            # Default values
            id=${id:-"N/A"}
            addr=${addr:-"N/A"}
            age=${age:-"N/A"}
            cmd=${cmd:-"N/A"}
            mem=${mem:-"N/A"}
            db=${db:-"0"}
            name=${name:-"N/A"}
            
            printf "  %-5s %-20s %-8s %-15s %-10s %-15s %s\n" "$id" "$addr" "$age" "$cmd" "$mem" "$db" "$name"
        fi
    done
else
    echo "  No active clients found"
fi

echo

print_header "REDIS STATISTICS"

print_subheader "OPERATIONS"
echo "$STATS_INFO" | grep -E "(total_commands_processed|instantaneous_ops_per_sec|total_net_input_bytes|total_net_output_bytes|rejected_connections|expired_keys|evicted_keys)" | while IFS=':' read -r key value; do
    case $key in
        "total_net_input_bytes"|"total_net_output_bytes")
            # Convert bytes to human readable format
            if [ "$value" -gt 1073741824 ]; then
                human_value=$(echo "scale=2; $value / 1073741824" | bc -l 2>/dev/null || echo "N/A")
                format_kv "$key" "$value (${human_value}GB)"
            elif [ "$value" -gt 1048576 ]; then
                human_value=$(echo "scale=2; $value / 1048576" | bc -l 2>/dev/null || echo "N/A")
                format_kv "$key" "$value (${human_value}MB)"
            else
                format_kv "$key" "$value"
            fi
            ;;
        *)
            format_kv "$key" "$value"
            ;;
    esac
done

echo

print_subheader "KEYSPACE"
if [ -n "$KEYSPACE_INFO" ] && echo "$KEYSPACE_INFO" | grep -q "db"; then
    echo "$KEYSPACE_INFO" | grep -E "db[0-9]+" | while IFS=':' read -r key value; do
        format_kv "$key" "$value"
    done
else
    echo "  No databases with keys found"
fi

echo

print_header "PERFORMANCE METRICS"

# Calculate performance metrics
total_ops=$(echo "$STATS_INFO" | grep "total_commands_processed" | cut -d':' -f2)
uptime=$(echo "$SERVER_INFO" | grep "uptime_in_seconds" | cut -d':' -f2)
connected_clients=$(echo "$CLIENTS_INFO" | grep "connected_clients" | cut -d':' -f2)
instant_ops=$(echo "$STATS_INFO" | grep "instantaneous_ops_per_sec" | cut -d':' -f2)

if [ -n "$total_ops" ] && [ -n "$uptime" ] && [ "$uptime" -gt 0 ]; then
    avg_ops=$(echo "scale=2; $total_ops / $uptime" | bc -l 2>/dev/null || echo "N/A")
    format_kv "Average Ops/Sec" "$avg_ops"
fi

format_kv "Current Ops/Sec" "$instant_ops"
format_kv "Connected Clients" "$connected_clients"
format_kv "Total Commands" "$total_ops"
format_kv "Uptime (seconds)" "$uptime"

echo

print_header "REDIS CONFIGURATION CHECK"

# Check some important configuration values
print_subheader "MEMORY POLICY"
MAXMEMORY=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw CONFIG GET maxmemory)
MAXMEMORY_POLICY=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw CONFIG GET maxmemory-policy)

echo "$MAXMEMORY" | sed 'N;s/\n/ /' | while read -r key value; do
    if [ "$key" = "maxmemory" ]; then
        if [ "$value" = "0" ]; then
            format_kv "$key" "unlimited"
        else
            format_kv "$key" "$value"
        fi
    fi
done

echo "$MAXMEMORY_POLICY" | sed 'N;s/\n/ /' | while read -r key value; do
    if [ "$key" = "maxmemory-policy" ]; then
        format_kv "$key" "$value"
    fi
done

echo

print_subheader "PERSISTENCE"
SAVE_CONFIG=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw CONFIG GET save)
AOF_CONFIG=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw CONFIG GET appendonly)

echo "$SAVE_CONFIG" | sed 'N;s/\n/ /' | while read -r key value; do
    if [ "$key" = "save" ]; then
        format_kv "RDB snapshots" "${value:-"disabled"}"
    fi
done

echo "$AOF_CONFIG" | sed 'N;s/\n/ /' | while read -r key value; do
    if [ "$key" = "appendonly" ]; then
        format_kv "AOF persistence" "$value"
    fi
done

echo

print_header "HEALTH CHECK"

# Simple health check
PING_RESULT=$(run_docker exec -it ${CONTAINER_NAME} redis-cli --raw ping 2>/dev/null)
if [ "$PING_RESULT" = "PONG" ]; then
    echo -e "  ${GREEN}✓ Redis is responding to ping${NC}"
else
    echo -e "  ${RED}✗ Redis is not responding to ping${NC}"
fi

# Check if Redis is accepting connections
if [ "$connected_clients" -ge 1 ]; then
    echo -e "  ${GREEN}✓ Redis is accepting connections${NC}"
else
    echo -e "  ${YELLOW}⚠ No clients currently connected${NC}"
fi

# Check memory usage
used_memory=$(echo "$MEMORY_INFO" | grep "used_memory:" | cut -d':' -f2)
if [ -n "$used_memory" ] && [ "$used_memory" -lt 1073741824 ]; then  # Less than 1GB
    echo -e "  ${GREEN}✓ Memory usage is normal${NC}"
else
    echo -e "  ${YELLOW}⚠ High memory usage detected${NC}"
fi

echo
echo -e "${CYAN}Redis monitoring completed successfully!${NC}"
echo -e "${CYAN}Run with: bash redis_monitor.sh${NC}"